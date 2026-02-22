"""Yahoo OAuth2 authentication helpers."""

import asyncio
import base64
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.models import UserAccount

logger = logging.getLogger(__name__)

YAHOO_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"

_refresh_lock = asyncio.Lock()


def get_authorization_url() -> str:
    """Build the Yahoo OAuth2 consent URL."""
    params = {
        "client_id": settings.yahoo_client_id,
        "redirect_uri": settings.yahoo_redirect_uri,
        "response_type": "code",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{YAHOO_AUTH_URL}?{qs}"


def _basic_auth_header() -> str:
    """HTTP Basic auth header value for Yahoo token requests."""
    creds = f"{settings.yahoo_client_id}:{settings.yahoo_client_secret}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


async def exchange_code_for_tokens(code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            YAHOO_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.yahoo_redirect_uri,
            },
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Use a refresh token to get a new access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            YAHOO_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def store_tokens(db: AsyncSession, token_data: dict) -> None:
    """Upsert tokens into user_accounts (single-user app, id=1)."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])

    result = await db.execute(select(UserAccount).where(UserAccount.id == 1))
    account = result.scalar_one_or_none()

    if account:
        account.yahoo_access_token = token_data["access_token"]
        account.yahoo_refresh_token = token_data["refresh_token"]
        account.yahoo_token_expires_at = expires_at
        account.updated_at = datetime.now(timezone.utc)
    else:
        account = UserAccount(
            id=1,
            yahoo_access_token=token_data["access_token"],
            yahoo_refresh_token=token_data["refresh_token"],
            yahoo_token_expires_at=expires_at,
        )
        db.add(account)

    await db.commit()
    logger.info("Yahoo tokens stored successfully.")


async def get_valid_token(db: AsyncSession) -> str | None:
    """Return a valid access token, refreshing if it expires within 5 minutes.

    Uses an asyncio.Lock to prevent concurrent refresh races.
    """
    async with _refresh_lock:
        result = await db.execute(select(UserAccount).where(UserAccount.id == 1))
        account = result.scalar_one_or_none()

        if not account:
            return None

        now = datetime.now(timezone.utc)
        expires_at = account.yahoo_token_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at and expires_at > now + timedelta(minutes=5):
            return account.yahoo_access_token

        # Token expired or about to expire — refresh
        logger.info("Refreshing Yahoo access token...")
        try:
            token_data = await refresh_access_token(account.yahoo_refresh_token)
            await store_tokens(db, token_data)
            return token_data["access_token"]
        except httpx.HTTPStatusError:
            logger.exception("Failed to refresh Yahoo token.")
            return None
