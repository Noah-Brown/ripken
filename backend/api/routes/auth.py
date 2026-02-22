"""Yahoo OAuth2 authentication routes."""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.database.models import UserAccount
from backend.yahoo.auth import exchange_code_for_tokens, get_authorization_url, store_tokens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/yahoo")
async def yahoo_login():
    """Redirect user to Yahoo consent page."""
    return RedirectResponse(get_authorization_url())


@router.get("/yahoo/callback")
async def yahoo_callback(code: str, db: AsyncSession = Depends(get_db_session)):
    """Exchange authorization code for tokens and sync data."""
    token_data = await exchange_code_for_tokens(code)
    await store_tokens(db, token_data)

    # Sync leagues and rosters immediately so data is ready
    try:
        from backend.yahoo.sync import sync_all_rosters, sync_leagues

        await sync_leagues(db)
        await sync_all_rosters(db)
    except Exception:
        logger.exception("Post-auth sync failed (non-blocking).")

    return RedirectResponse("http://localhost:3000/?yahoo_connected=1")


@router.get("/yahoo/status")
async def yahoo_status(db: AsyncSession = Depends(get_db_session)):
    """Check if Yahoo account is connected."""
    result = await db.execute(select(UserAccount).where(UserAccount.id == 1))
    account = result.scalar_one_or_none()
    return {"connected": account is not None}
