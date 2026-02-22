"""Map Yahoo Fantasy players to internal player IDs."""

import difflib
import logging
import re

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import Player

logger = logging.getLogger(__name__)

# Yahoo sometimes uses different team abbreviations than MLB.
# Populate as discrepancies are discovered.
YAHOO_TEAM_MAP: dict[str, str] = {
    "Was": "WSH",
    "WSN": "WSH",
    "CWS": "CHW",
    "CHC": "CHC",
    "SF": "SF",
    "SD": "SD",
    "KC": "KC",
    "TB": "TB",
    "LAA": "LAA",
    "LAD": "LAD",
}

_SUFFIX_RE = re.compile(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)$", re.IGNORECASE)


def _normalize_name(name: str) -> str:
    """Lowercase and strip suffixes like Jr., III, etc."""
    name = name.strip().lower()
    name = _SUFFIX_RE.sub("", name)
    return name


def _normalize_team(team: str) -> str:
    """Normalize a Yahoo team abbreviation to our internal format."""
    return YAHOO_TEAM_MAP.get(team, team)


async def match_yahoo_player(
    db: AsyncSession,
    yahoo_name: str,
    yahoo_team: str,
    yahoo_position: str,
    yahoo_player_key: str,
    league_slot: int,
) -> int | None:
    """Try to match a Yahoo player to an internal player ID.

    Returns the player ID if matched, None otherwise.
    Matching strategy:
      1. Exact name + exact team -> high confidence
      2. Exact name + any team (traded?) -> medium
      3. Fuzzy name (>0.85) + exact team -> medium
      4. No match -> log warning, return None
    """
    norm_name = _normalize_name(yahoo_name)
    norm_team = _normalize_team(yahoo_team)

    # Load all players for matching
    result = await db.execute(select(Player))
    all_players = result.scalars().all()

    best_match: Player | None = None
    best_score = 0.0

    for player in all_players:
        player_name = _normalize_name(player.full_name)
        player_team = player.team or ""

        # Exact name match
        if player_name == norm_name:
            if player_team == norm_team:
                # Strategy 1: exact name + exact team
                best_match = player
                break
            else:
                # Strategy 2: exact name, different team (trade?)
                if best_score < 0.95:
                    best_match = player
                    best_score = 0.95

        # Fuzzy name match
        elif best_score < 0.9:
            ratio = difflib.SequenceMatcher(None, player_name, norm_name).ratio()
            if ratio > 0.85 and player_team == norm_team and ratio > best_score:
                best_match = player
                best_score = ratio

    if best_match is None:
        logger.warning(f"No match for Yahoo player: {yahoo_name} ({yahoo_team}, {yahoo_position})")
        return None

    # Store the yahoo player key in the appropriate slot
    yahoo_id_col = f"yahoo_id_{league_slot}"
    try:
        yahoo_id_val = int(yahoo_player_key.split(".")[-1]) if "." in yahoo_player_key else int(yahoo_player_key)
    except (ValueError, IndexError):
        yahoo_id_val = None

    if yahoo_id_val is not None:
        await db.execute(
            update(Player)
            .where(Player.id == best_match.id)
            .values(**{yahoo_id_col: yahoo_id_val})
        )

    return best_match.id


async def map_roster_players(
    db: AsyncSession,
    yahoo_players: list[dict],
    league_slot: int,
) -> tuple[list[dict], list[dict]]:
    """Batch-map Yahoo roster players to internal IDs.

    Returns (matched, unmatched) lists. Each item is the original yahoo_player
    dict with an added 'internal_player_id' key (or None for unmatched).
    """
    matched = []
    unmatched = []

    for yp in yahoo_players:
        name_data = yp.get("name", {})
        yahoo_name = name_data.get("full", "") if isinstance(name_data, dict) else str(name_data)
        yahoo_team = yp.get("editorial_team_abbr", "")
        yahoo_position = yp.get("display_position", "")
        yahoo_player_key = yp.get("player_key", "")

        player_id = await match_yahoo_player(
            db, yahoo_name, yahoo_team, yahoo_position, yahoo_player_key, league_slot
        )

        entry = {**yp, "internal_player_id": player_id}
        if player_id is not None:
            matched.append(entry)
        else:
            unmatched.append(entry)

    logger.info(f"Player mapping: {len(matched)} matched, {len(unmatched)} unmatched")
    return matched, unmatched
