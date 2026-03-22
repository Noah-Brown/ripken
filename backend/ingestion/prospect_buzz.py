"""Prospect call-up buzz ingestion from RSS feeds.

Monitors baseball news RSS feeds for articles mentioning watched prospects
in the context of potential call-ups, promotions, or roster moves.
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import Player, Prospect, ProspectBuzz

logger = logging.getLogger(__name__)

# RSS feeds to monitor for prospect call-up news
RSS_FEEDS = [
    {
        "url": "https://www.mlb.com/feeds/news/rss.xml",
        "source": "mlb.com",
    },
    {
        "url": "https://www.espn.com/espn/rss/mlb/news",
        "source": "espn",
    },
    {
        "url": "https://www.baseballamerica.com/feed/",
        "source": "baseballamerica",
    },
    {
        "url": "https://blogs.fangraphs.com/feed/",
        "source": "fangraphs",
    },
]

# Phrases that signal call-up buzz when found near a prospect's name
CALLUP_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"call[- ]?up",
        r"promot(?:ed|ion|ing)",
        r"set to join",
        r"expected to (?:be called|join|arrive|debut)",
        r"imminent",
        r"(?:MLB|big[- ]?league) debut",
        r"likely to be (?:promoted|called)",
        r"on the verge",
        r"nearing (?:a |the )?call",
        r"(?:roster |service time )manipulation",
        r"join(?:ing)? the (?:club|roster|team|big leagues)",
        r"(?:top|#\d+) prospect.*(?:ready|close|soon|near)",
        r"fast[- ]?track",
        r"added to (?:the )?(?:40|25)[- ]?man",
        r"option(?:ed|ing).*(?:make room|clear)",
    ]
]


def _extract_text(element: ET.Element, tag: str) -> str:
    """Safely extract text from an XML element."""
    child = element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _parse_rss_date(date_str: str) -> datetime | None:
    """Parse common RSS date formats."""
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _has_callup_language(text: str) -> bool:
    """Check if text contains call-up related language."""
    return any(pattern.search(text) for pattern in CALLUP_PATTERNS)


def _extract_snippet(text: str, player_name: str, max_len: int = 300) -> str:
    """Extract a relevant snippet around where the player name appears."""
    idx = text.lower().find(player_name.lower())
    if idx == -1:
        # Fallback: find near call-up language
        for pattern in CALLUP_PATTERNS:
            match = pattern.search(text)
            if match:
                idx = match.start()
                break
    if idx == -1:
        return text[:max_len].strip()

    start = max(0, idx - 80)
    end = min(len(text), idx + max_len - 80)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


async def fetch_prospect_buzz(db: AsyncSession) -> int:
    """Fetch RSS feeds, match articles to watched prospects, and store buzz.

    Returns the number of new buzz items stored.
    """
    # Load watched prospects with player names
    result = await db.execute(
        select(Prospect, Player)
        .join(Player, Prospect.player_id == Player.id)
    )
    prospect_rows = result.all()
    if not prospect_rows:
        return 0

    # Build lookup: map name parts to (player_id, full_name) for matching
    prospect_lookup: dict[str, tuple[int, str]] = {}
    for prospect, player in prospect_rows:
        name = player.full_name.strip()
        # Use full name and last name for matching
        prospect_lookup[name.lower()] = (player.id, name)
        parts = name.split()
        if len(parts) >= 2:
            last = parts[-1]
            if len(last) > 3:  # Avoid short last names like "Lee" matching too broadly
                prospect_lookup[last.lower()] = (player.id, name)

    # Cutoff: only consider articles from the last 7 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    new_count = 0

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for feed in RSS_FEEDS:
            try:
                resp = await client.get(feed["url"])
                resp.raise_for_status()
            except httpx.HTTPError:
                logger.warning(f"Failed to fetch RSS feed: {feed['source']}")
                continue

            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError:
                logger.warning(f"Failed to parse RSS feed: {feed['source']}")
                continue

            # Handle both RSS 2.0 (<channel><item>) and Atom (<entry>) formats
            items = root.findall(".//item") or root.findall(
                ".//{http://www.w3.org/2005/Atom}entry"
            )

            for item in items:
                title = _extract_text(item, "title")
                link = (
                    _extract_text(item, "link")
                    or _extract_text(item, "guid")
                )
                description = (
                    _extract_text(item, "description")
                    or _extract_text(item, "summary")
                    or ""
                )
                pub_date_str = (
                    _extract_text(item, "pubDate")
                    or _extract_text(item, "published")
                    or ""
                )

                # Handle Atom links which use href attribute
                if not link:
                    link_elem = item.find("link")
                    if link_elem is not None:
                        link = link_elem.get("href", "")

                if not title or not link:
                    continue

                pub_date = _parse_rss_date(pub_date_str) if pub_date_str else None
                if pub_date and pub_date.replace(tzinfo=timezone.utc) < cutoff:
                    continue

                # Combine title + description for matching
                combined = f"{title} {description}"

                # Check if this article mentions any watched prospect
                # AND contains call-up language
                if not _has_callup_language(combined):
                    continue

                for name_key, (player_id, full_name) in prospect_lookup.items():
                    if name_key not in combined.lower():
                        continue

                    # Full-name match preferred; for last-name-only, require
                    # the last name to appear as a whole word
                    if " " not in name_key:
                        if not re.search(
                            rf"\b{re.escape(name_key)}\b", combined, re.IGNORECASE
                        ):
                            continue

                    # Check if we already have this URL
                    existing = await db.execute(
                        select(ProspectBuzz).where(ProspectBuzz.url == link)
                    )
                    if existing.scalar_one_or_none():
                        continue

                    snippet = _extract_snippet(description or title, full_name)

                    buzz = ProspectBuzz(
                        player_id=player_id,
                        source=feed["source"],
                        title=title,
                        url=link,
                        snippet=snippet,
                        published_at=pub_date,
                    )
                    db.add(buzz)
                    new_count += 1
                    logger.info(
                        f"New buzz for {full_name}: {title[:80]} ({feed['source']})"
                    )
                    break  # One buzz entry per article

    await db.commit()
    logger.info(f"Prospect buzz scan complete: {new_count} new items")
    return new_count
