"""MLB Stats API client for ingesting schedule, roster, and game data."""

import argparse
import asyncio
import logging
from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.connection import async_session
from backend.database.models import (
    Game,
    PitcherAppearance,
    Player,
    ProbablePitcher,
    Transaction,
)

logger = logging.getLogger(__name__)

BASE_URL = settings.mlb_stats_api_base

# MLB status code -> our normalized status
STATUS_MAP = {
    "S": "scheduled",
    "P": "scheduled",   # Pre-Game still counts as scheduled
    "I": "live",
    "F": "final",
    "O": "final",       # Game over, not yet officially final
    "D": "postponed",
    "DR": "postponed",
}

# MLB transaction typeCode -> our normalized type
TRANSACTION_TYPE_MAP = {
    "CU": "call_up",
    "ASS": "option",
    "OPT": "option",
    "DES": "DFA",
    "DL": "IL",
    "IL": "IL",
    "RTN": "IL_return",
    "ACT": "IL_return",
    "TR": "trade",
    "REL": "release",
    "SC": "call_up",
    "RL": "release",
    "SGN": "call_up",
}


async def _get(client: httpx.AsyncClient, path: str, params: dict | None = None) -> dict:
    """Make a GET request to the MLB Stats API and return JSON."""
    url = f"{BASE_URL}{path}"
    resp = await client.get(url, params=params, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Schedule
# ---------------------------------------------------------------------------


async def fetch_schedule(db: AsyncSession, start_date: str, end_date: str) -> None:
    """Fetch games from the MLB schedule endpoint and upsert into the games table."""
    async with httpx.AsyncClient() as client:
        data = await _get(client, "/schedule", params={
            "sportId": 1,
            "startDate": start_date,
            "endDate": end_date,
            "hydrate": "probablePitcher,team",
        })

    games_to_upsert = []
    for date_entry in data.get("dates", []):
        game_date = date_entry.get("date", "")
        for game in date_entry.get("games", []):
            game_pk = game.get("gamePk")
            if not game_pk:
                continue

            status_code = game.get("status", {}).get("statusCode", "S")
            status = STATUS_MAP.get(status_code, "scheduled")

            home_team_data = game.get("teams", {}).get("home", {}).get("team", {})
            away_team_data = game.get("teams", {}).get("away", {}).get("team", {})

            home_score = game.get("teams", {}).get("home", {}).get("score")
            away_score = game.get("teams", {}).get("away", {}).get("score")

            games_to_upsert.append({
                "id": game_pk,
                "date": game_date,
                "home_team": home_team_data.get("abbreviation", ""),
                "away_team": away_team_data.get("abbreviation", ""),
                "status": status,
                "home_score": home_score,
                "away_score": away_score,
                "venue": game.get("venue", {}).get("name", ""),
                "game_time": game.get("gameDate", ""),
            })

    for row in games_to_upsert:
        stmt = sqlite_insert(Game).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "status": stmt.excluded.status,
                "home_score": stmt.excluded.home_score,
                "away_score": stmt.excluded.away_score,
                "game_time": stmt.excluded.game_time,
                "venue": stmt.excluded.venue,
            },
        )
        await db.execute(stmt)

    await db.commit()
    logger.info("Upserted %d games for %s to %s", len(games_to_upsert), start_date, end_date)


# ---------------------------------------------------------------------------
# 2. Rosters
# ---------------------------------------------------------------------------


async def fetch_rosters(db: AsyncSession) -> None:
    """Fetch active rosters for all 30 MLB teams and update player status."""
    async with httpx.AsyncClient() as client:
        teams_data = await _get(client, "/teams", params={"sportId": 1})
        teams = teams_data.get("teams", [])

        active_mlb_ids: set[int] = set()

        for team in teams:
            team_id = team.get("id")
            team_abbr = team.get("abbreviation", "")
            if not team_id:
                continue

            try:
                roster_data = await _get(client, f"/teams/{team_id}/roster", params={
                    "rosterType": "active",
                })
            except httpx.HTTPStatusError as exc:
                logger.warning("Failed to fetch roster for team %s (%s): %s", team_abbr, team_id, exc)
                await asyncio.sleep(1)
                continue

            for entry in roster_data.get("roster", []):
                person = entry.get("person", {})
                mlb_id = person.get("id")
                if not mlb_id:
                    continue

                active_mlb_ids.add(mlb_id)
                full_name = person.get("fullName", "")
                position = entry.get("position", {}).get("abbreviation", "")

                stmt = sqlite_insert(Player).values(
                    mlb_id=mlb_id,
                    full_name=full_name,
                    team=team_abbr,
                    position=position,
                    status="active",
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["mlb_id"],
                    set_={
                        "full_name": stmt.excluded.full_name,
                        "team": stmt.excluded.team,
                        "position": stmt.excluded.position,
                        "status": "active",
                    },
                )
                await db.execute(stmt)

            await asyncio.sleep(1)  # rate limit

        # Mark players not on any active roster as inactive
        if active_mlb_ids:
            result = await db.execute(
                select(Player).where(
                    Player.mlb_id.isnot(None),
                    Player.mlb_id.notin_(active_mlb_ids),
                    Player.status == "active",
                )
            )
            for player in result.scalars().all():
                player.status = "inactive"

        await db.commit()
        logger.info("Updated rosters: %d active players across %d teams", len(active_mlb_ids), len(teams))


# ---------------------------------------------------------------------------
# 3. Probable Pitchers
# ---------------------------------------------------------------------------


async def fetch_probable_pitchers(db: AsyncSession, start_date: str, end_date: str) -> None:
    """Extract probable pitchers from schedule data and upsert into probable_pitchers table."""
    async with httpx.AsyncClient() as client:
        data = await _get(client, "/schedule", params={
            "sportId": 1,
            "startDate": start_date,
            "endDate": end_date,
            "hydrate": "probablePitcher,team",
        })

    count = 0
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            game_pk = game.get("gamePk")
            if not game_pk:
                continue

            for side in ("away", "home"):
                team_data = game.get("teams", {}).get(side, {})
                pitcher = team_data.get("probablePitcher", {})
                pitcher_mlb_id = pitcher.get("id")
                team_abbr = team_data.get("team", {}).get("abbreviation", "")

                if not pitcher_mlb_id or not team_abbr:
                    continue

                # Ensure the player exists in our players table
                result = await db.execute(
                    select(Player.id).where(Player.mlb_id == pitcher_mlb_id)
                )
                player_row = result.scalar_one_or_none()

                if player_row is None:
                    # Insert a minimal player record
                    ins = sqlite_insert(Player).values(
                        mlb_id=pitcher_mlb_id,
                        full_name=pitcher.get("fullName", "Unknown"),
                        team=team_abbr,
                        position="P",
                        status="active",
                    )
                    ins = ins.on_conflict_do_nothing(index_elements=["mlb_id"])
                    await db.execute(ins)
                    await db.flush()
                    result = await db.execute(
                        select(Player.id).where(Player.mlb_id == pitcher_mlb_id)
                    )
                    player_row = result.scalar_one_or_none()

                if player_row is None:
                    continue

                player_id = player_row

                stmt = sqlite_insert(ProbablePitcher).values(
                    game_id=game_pk,
                    team=team_abbr,
                    player_id=player_id,
                    is_confirmed=1,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["game_id", "team"],
                    set_={
                        "player_id": stmt.excluded.player_id,
                        "is_confirmed": stmt.excluded.is_confirmed,
                    },
                )
                await db.execute(stmt)
                count += 1

    await db.commit()
    logger.info("Upserted %d probable pitcher entries for %s to %s", count, start_date, end_date)


# ---------------------------------------------------------------------------
# 4. Transactions
# ---------------------------------------------------------------------------


async def fetch_transactions(db: AsyncSession, start_date: str, end_date: str) -> None:
    """Fetch transactions from the MLB API and insert into the transactions table."""
    async with httpx.AsyncClient() as client:
        data = await _get(client, "/transactions", params={
            "startDate": start_date,
            "endDate": end_date,
        })

    count = 0
    for txn in data.get("transactions", []):
        type_code = txn.get("typeCode", "")
        mapped_type = TRANSACTION_TYPE_MAP.get(type_code)
        if not mapped_type:
            continue

        person = txn.get("person", {})
        player_mlb_id = person.get("id")
        player_name = person.get("fullName", "")

        # Look up internal player_id if we have this player
        player_id = None
        if player_mlb_id:
            result = await db.execute(
                select(Player.id).where(Player.mlb_id == player_mlb_id)
            )
            player_id = result.scalar_one_or_none()

        from_team = txn.get("fromTeam", {}).get("abbreviation", "")
        to_team = txn.get("toTeam", {}).get("abbreviation", "")
        txn_date = txn.get("date", "")
        if txn_date and "T" in txn_date:
            txn_date = txn_date.split("T")[0]

        description = txn.get("description", "")
        mlb_txn_id = txn.get("id")

        new_txn = Transaction(
            mlb_transaction_id=mlb_txn_id,
            date=txn_date,
            player_id=player_id,
            player_name=player_name,
            type=mapped_type,
            from_team=from_team,
            to_team=to_team,
            description=description,
        )
        db.add(new_txn)
        count += 1

    await db.commit()
    logger.info("Inserted %d transactions for %s to %s", count, start_date, end_date)


# ---------------------------------------------------------------------------
# 5. Game Results (pitcher appearances from box score)
# ---------------------------------------------------------------------------


def _parse_ip(ip_str: str) -> float:
    """Convert innings pitched string like '6.2' to proper float (6.2 -> 6.667)."""
    try:
        parts = str(ip_str).split(".")
        if len(parts) == 2:
            full = int(parts[0])
            thirds = int(parts[1])
            return round(full + thirds / 3.0, 3)
        return float(ip_str)
    except (ValueError, TypeError):
        return 0.0


async def fetch_game_results(db: AsyncSession, game_id: int) -> None:
    """Fetch live game feed and extract pitcher appearance data from the boxscore."""
    # Game feed uses v1.1 endpoint, not v1
    feed_url = f"https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live"
    async with httpx.AsyncClient() as client:
        resp = await client.get(feed_url, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

    game_data = data.get("gameData", {})
    game_date = game_data.get("datetime", {}).get("officialDate", "")

    boxscore = data.get("liveData", {}).get("boxscore", {})
    teams_box = boxscore.get("teams", {})

    count = 0
    for side in ("away", "home"):
        team_box = teams_box.get(side, {})
        pitcher_ids = team_box.get("pitchers", [])
        players_data = team_box.get("players", {})

        for pid in pitcher_ids:
            player_key = f"ID{pid}"
            player_info = players_data.get(player_key, {})
            if not player_info:
                continue

            person = player_info.get("person", {})
            mlb_id = person.get("id", pid)

            stats = player_info.get("stats", {}).get("pitching", {})
            if not stats:
                continue

            # Look up internal player_id
            result = await db.execute(
                select(Player.id).where(Player.mlb_id == mlb_id)
            )
            player_id = result.scalar_one_or_none()

            if player_id is None:
                # Insert a minimal player record
                ins = sqlite_insert(Player).values(
                    mlb_id=mlb_id,
                    full_name=person.get("fullName", "Unknown"),
                    position="P",
                    status="active",
                )
                ins = ins.on_conflict_do_nothing(index_elements=["mlb_id"])
                await db.execute(ins)
                await db.flush()
                result = await db.execute(
                    select(Player.id).where(Player.mlb_id == mlb_id)
                )
                player_id = result.scalar_one_or_none()

            if player_id is None:
                continue

            ip_str = stats.get("inningsPitched", "0")
            innings_pitched = _parse_ip(ip_str)

            row = {
                "player_id": player_id,
                "game_id": game_id,
                "date": game_date,
                "innings_pitched": innings_pitched,
                "pitches": int(stats.get("numberOfPitches", 0)),
                "earned_runs": int(stats.get("earnedRuns", 0)),
                "strikeouts": int(stats.get("strikeOuts", 0)),
                "walks": int(stats.get("baseOnBalls", 0)),
                "hits_allowed": int(stats.get("hits", 0)),
                "save": 1 if stats.get("saves", 0) else 0,
                "hold": 1 if stats.get("holds", 0) else 0,
                "blown_save": 1 if stats.get("blownSaves", 0) else 0,
                "inherited_runners": int(stats.get("inheritedRunners", 0)),
                "inherited_scored": int(stats.get("inheritedRunnersScored", 0)),
                "is_starter": 1 if stats.get("gamesStarted", 0) else 0,
            }

            stmt = sqlite_insert(PitcherAppearance).values(**row)
            stmt = stmt.on_conflict_do_update(
                index_elements=["player_id", "game_id"],
                set_={
                    "innings_pitched": stmt.excluded.innings_pitched,
                    "pitches": stmt.excluded.pitches,
                    "earned_runs": stmt.excluded.earned_runs,
                    "strikeouts": stmt.excluded.strikeouts,
                    "walks": stmt.excluded.walks,
                    "hits_allowed": stmt.excluded.hits_allowed,
                    "save": stmt.excluded.save,
                    "hold": stmt.excluded.hold,
                    "blown_save": stmt.excluded.blown_save,
                    "inherited_runners": stmt.excluded.inherited_runners,
                    "inherited_scored": stmt.excluded.inherited_scored,
                    "is_starter": stmt.excluded.is_starter,
                },
            )
            await db.execute(stmt)
            count += 1

    await db.commit()
    logger.info("Upserted %d pitcher appearances for game %d", count, game_id)


async def fetch_all_game_results(db: AsyncSession) -> None:
    """Find all final games without pitcher appearances and ingest them."""
    result = await db.execute(
        select(Game.id).where(
            Game.status == "final",
            ~Game.id.in_(
                select(PitcherAppearance.game_id).distinct()
            ),
        )
    )
    game_ids = [row[0] for row in result.all()]

    if not game_ids:
        logger.info("No unprocessed final games found")
        return

    logger.info("Found %d unprocessed final games", len(game_ids))
    for game_id in game_ids:
        try:
            await fetch_game_results(db, game_id)
        except Exception:
            logger.exception("Failed to ingest game %d", game_id)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(description="MLB Stats API ingestion client")
    parser.add_argument(
        "--action",
        required=True,
        choices=["schedule", "rosters", "probable_pitchers", "transactions", "game_results"],
        help="Which data to fetch",
    )
    parser.add_argument("--start-date", default=str(date.today()), help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=str(date.today()), help="End date (YYYY-MM-DD)")
    parser.add_argument("--game-id", type=int, help="Game PK (for game_results action)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    async with async_session() as db:
        if args.action == "schedule":
            await fetch_schedule(db, args.start_date, args.end_date)
        elif args.action == "rosters":
            await fetch_rosters(db)
        elif args.action == "probable_pitchers":
            await fetch_probable_pitchers(db, args.start_date, args.end_date)
        elif args.action == "transactions":
            await fetch_transactions(db, args.start_date, args.end_date)
        elif args.action == "game_results":
            if not args.game_id:
                parser.error("--game-id is required for game_results action")
            await fetch_game_results(db, args.game_id)


if __name__ == "__main__":
    asyncio.run(main())
