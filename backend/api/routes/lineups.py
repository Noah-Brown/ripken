"""Lineup tracker API routes."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.database.models import (
    Game,
    Lineup,
    Player,
    ProbablePitcher,
    UserLeague,
    UserRoster,
    UserWatchlist,
)

router = APIRouter(prefix="/api", tags=["lineups"])


async def _get_roster_player_ids(db: AsyncSession) -> set[int]:
    """Get all player IDs on the user's rosters across leagues."""
    result = await db.execute(select(UserRoster.player_id).where(UserRoster.player_id.isnot(None)))
    return {row[0] for row in result.all()}


async def _get_watchlist_player_ids(db: AsyncSession) -> set[int]:
    """Get all player IDs on the user's watchlist."""
    result = await db.execute(select(UserWatchlist.player_id))
    return {row[0] for row in result.all()}


async def _get_free_agent_ids(db: AsyncSession) -> set[int]:
    """Get IDs of active players NOT on any user roster."""
    roster_ids = await _get_roster_player_ids(db)
    result = await db.execute(
        select(Player.id).where(Player.status == "active")
    )
    all_active = {row[0] for row in result.all()}
    return all_active - roster_ids


@router.get("/lineups/today")
async def get_lineups_today(db: AsyncSession = Depends(get_db_session)):
    """All today's games with lineup data, annotated with fantasy relevance."""
    today = date.today().isoformat()

    # Load user context
    roster_ids = await _get_roster_player_ids(db)
    watchlist_ids = await _get_watchlist_player_ids(db)

    # Get today's games
    games_result = await db.execute(
        select(Game).where(Game.date == today).order_by(Game.game_time)
    )
    games = games_result.scalars().all()

    response = []
    for game in games:
        # Probable pitchers
        pp_result = await db.execute(
            select(ProbablePitcher, Player)
            .join(Player, ProbablePitcher.player_id == Player.id)
            .where(ProbablePitcher.game_id == game.id)
        )
        pitcher_map = {}
        for pp, player in pp_result.all():
            pitcher_map[pp.team] = {
                "name": player.full_name,
                "mlb_id": player.mlb_id,
                "player_id": player.id,
                "team": pp.team,
                "is_confirmed": bool(pp.is_confirmed),
                "relevance": _player_relevance(player.id, roster_ids, watchlist_ids),
            }

        # Lineups for both teams
        teams_data = {}
        for team in [game.home_team, game.away_team]:
            lineup_result = await db.execute(
                select(Lineup, Player)
                .join(Player, Lineup.player_id == Player.id)
                .where(Lineup.game_id == game.id, Lineup.team == team)
                .order_by(Lineup.batting_order)
            )
            lineup_rows = lineup_result.all()

            players_list = []
            for lineup_entry, player in lineup_rows:
                players_list.append({
                    "player_id": player.id,
                    "full_name": player.full_name,
                    "position": player.position,
                    "batting_order": lineup_entry.batting_order,
                    "is_confirmed": bool(lineup_entry.is_confirmed),
                    "relevance": _player_relevance(player.id, roster_ids, watchlist_ids),
                })

            teams_data[team] = {
                "lineup": players_list,
                "has_my_player": any(p["relevance"] == "roster" for p in players_list),
            }

        response.append({
            "game_id": game.id,
            "date": game.date,
            "game_time": game.game_time,
            "home_team": game.home_team,
            "away_team": game.away_team,
            "status": game.status,
            "home_score": game.home_score,
            "away_score": game.away_score,
            "venue": game.venue,
            "probable_pitchers": {
                "home": pitcher_map.get(game.home_team),
                "away": pitcher_map.get(game.away_team),
            },
            "teams": teams_data,
            "has_my_player": (
                teams_data.get(game.home_team, {}).get("has_my_player", False)
                or teams_data.get(game.away_team, {}).get("has_my_player", False)
            ),
        })

    return {"date": today, "games": response}


def _player_relevance(player_id: int, roster_ids: set[int], watchlist_ids: set[int]) -> str:
    """Classify a player's fantasy relevance for color coding."""
    if player_id in roster_ids:
        return "roster"
    if player_id in watchlist_ids:
        return "watchlist"
    return "other"
