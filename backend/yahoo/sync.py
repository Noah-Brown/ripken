"""Sync Yahoo Fantasy league and roster data to local DB."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import UserAccount, UserLeague, UserRoster
from backend.yahoo.client import get_league_settings, get_leagues, get_roster, get_team_key
from backend.yahoo.player_mapping import map_roster_players

logger = logging.getLogger(__name__)


async def sync_leagues(db: AsyncSession) -> list[UserLeague]:
    """Fetch leagues from Yahoo and upsert into user_leagues."""
    # Check that we have a connected Yahoo account
    result = await db.execute(select(UserAccount).where(UserAccount.id == 1))
    account = result.scalar_one_or_none()
    if not account:
        logger.info("No Yahoo account connected — skipping league sync.")
        return []

    leagues_data = await get_leagues(db)
    if not leagues_data:
        logger.info("No Yahoo leagues found.")
        return []

    synced = []
    for lg in leagues_data:
        league_key = lg.get("league_key", "")
        if not league_key:
            continue

        # Fetch settings for richer data
        settings_data = await get_league_settings(db, league_key)

        # Extract roster positions and scoring categories from settings
        roster_slots = None
        scoring_categories = None
        if isinstance(settings_data, dict):
            roster_pos = settings_data.get("roster_positions", [])
            if isinstance(roster_pos, list):
                roster_slots = json.dumps(roster_pos)
            elif isinstance(roster_pos, dict):
                # Sometimes it's a dict with count key
                positions = []
                for k, v in roster_pos.items():
                    if k != "count" and isinstance(v, dict):
                        positions.append(v.get("roster_position", v))
                roster_slots = json.dumps(positions)

            stat_cats = settings_data.get("stat_categories", {})
            if stat_cats:
                scoring_categories = json.dumps(stat_cats)

        # Upsert
        result = await db.execute(
            select(UserLeague).where(UserLeague.yahoo_league_key == league_key)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.league_name = lg.get("name", existing.league_name)
            existing.format = lg.get("scoring_type", existing.format or "head")
            existing.num_teams = lg.get("num_teams", existing.num_teams)
            existing.season = lg.get("season", existing.season)
            if roster_slots:
                existing.roster_slots = roster_slots
            if scoring_categories:
                existing.scoring_categories = scoring_categories
            existing.updated_at = datetime.now(timezone.utc)
            synced.append(existing)
        else:
            new_league = UserLeague(
                user_account_id=1,
                yahoo_league_key=league_key,
                league_name=lg.get("name"),
                format=lg.get("scoring_type", "head"),
                scoring_categories=scoring_categories,
                roster_slots=roster_slots,
                num_teams=lg.get("num_teams"),
                season=lg.get("season"),
            )
            db.add(new_league)
            synced.append(new_league)

    await db.commit()
    logger.info(f"Synced {len(synced)} Yahoo leagues.")
    return synced


async def sync_roster_for_league(
    db: AsyncSession, league: UserLeague, league_slot: int
) -> None:
    """Fetch and store roster for a single league.

    Does a full replace: deletes existing rows, re-inserts.
    """
    team_key = await get_team_key(db, league.yahoo_league_key)
    if not team_key:
        logger.warning(f"Could not find team key for league {league.yahoo_league_key}")
        return

    yahoo_players = await get_roster(db, team_key)
    if not yahoo_players:
        logger.info(f"No roster players for league {league.yahoo_league_key}")
        return

    matched, unmatched = await map_roster_players(db, yahoo_players, league_slot)

    # Delete existing roster entries for this league
    await db.execute(
        delete(UserRoster).where(UserRoster.league_id == league.id)
    )

    # Insert matched players
    for entry in matched:
        name_data = entry.get("name", {})
        roster = UserRoster(
            league_id=league.id,
            player_id=entry["internal_player_id"],
            yahoo_player_key=entry.get("player_key"),
            roster_position=entry.get("selected_position", ""),
            is_editable=1,
        )
        db.add(roster)

    # Insert unmatched players (player_id=None, stored for visibility)
    for entry in unmatched:
        roster = UserRoster(
            league_id=league.id,
            player_id=None,
            yahoo_player_key=entry.get("player_key"),
            roster_position=entry.get("selected_position", ""),
            is_editable=1,
        )
        db.add(roster)

    await db.commit()
    logger.info(
        f"Synced roster for league {league.league_name}: "
        f"{len(matched)} matched, {len(unmatched)} unmatched"
    )


async def sync_all_rosters(db: AsyncSession) -> None:
    """Sync rosters for all connected leagues."""
    # Check connection first
    result = await db.execute(select(UserAccount).where(UserAccount.id == 1))
    account = result.scalar_one_or_none()
    if not account:
        logger.info("No Yahoo account connected — skipping roster sync.")
        return

    result = await db.execute(select(UserLeague).where(UserLeague.user_account_id == 1))
    leagues = result.scalars().all()

    for idx, league in enumerate(leagues):
        # league_slot is 1-based (yahoo_id_1, yahoo_id_2)
        league_slot = idx + 1
        if league_slot > 2:
            logger.warning(f"Skipping league {league.league_name} — only 2 league slots supported.")
            continue
        await sync_roster_for_league(db, league, league_slot)
