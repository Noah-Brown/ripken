"""Roster and league API routes."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.database.models import Game, Player, PlayerStats, UserLeague, UserRoster

router = APIRouter(prefix="/api", tags=["roster"])


@router.get("/leagues")
async def get_leagues(db: AsyncSession = Depends(get_db_session)):
    """List connected Yahoo leagues."""
    result = await db.execute(select(UserLeague).order_by(UserLeague.id))
    leagues = result.scalars().all()
    return {
        "leagues": [
            {
                "id": lg.id,
                "yahoo_league_key": lg.yahoo_league_key,
                "name": lg.league_name,
                "format": lg.format,
                "num_teams": lg.num_teams,
                "season": lg.season,
            }
            for lg in leagues
        ]
    }


@router.get("/roster/{league_id}")
async def get_roster(league_id: int, db: AsyncSession = Depends(get_db_session)):
    """Roster for a league, enriched with today's game, stats, and start/sit scores."""
    today = date.today().isoformat()

    # Get roster entries with player data
    result = await db.execute(
        select(UserRoster, Player)
        .outerjoin(Player, UserRoster.player_id == Player.id)
        .where(UserRoster.league_id == league_id)
        .order_by(UserRoster.roster_position)
    )
    rows = result.all()

    # Load today's games for quick lookup
    games_result = await db.execute(select(Game).where(Game.date == today))
    games = games_result.scalars().all()
    team_games: dict[str, dict] = {}
    for game in games:
        team_games[game.home_team] = {
            "game_id": game.id,
            "opponent": game.away_team,
            "home_away": "home",
            "game_time": game.game_time,
            "status": game.status,
            "venue": game.venue,
        }
        team_games[game.away_team] = {
            "game_id": game.id,
            "opponent": game.home_team,
            "home_away": "away",
            "game_time": game.game_time,
            "status": game.status,
            "venue": game.venue,
        }

    roster_entries = []
    player_ids = [r.player_id for r, _ in rows if r.player_id is not None]

    # Batch-load latest fangraphs stats for all roster players
    stats_map: dict[int, dict] = {}
    if player_ids:
        stats_result = await db.execute(
            select(PlayerStats)
            .where(
                PlayerStats.player_id.in_(player_ids),
                PlayerStats.source == "fangraphs",
            )
            .order_by(PlayerStats.date.desc())
        )
        for stat in stats_result.scalars().all():
            if stat.player_id not in stats_map:
                stats_map[stat.player_id] = {
                    "date": stat.date,
                    "stat_type": stat.stat_type,
                    "stats": stat.stats,
                }

    # Compute start/sit scores for hitters
    start_sit_map: dict[int, dict] = {}
    if player_ids:
        from backend.analytics.start_sit import compute_start_sit_scores

        start_sit_map = await compute_start_sit_scores(db, player_ids)

    for roster_entry, player in rows:
        entry: dict = {
            "roster_position": roster_entry.roster_position,
            "yahoo_player_key": roster_entry.yahoo_player_key,
            "player": None,
            "today_game": None,
            "stats": None,
            "start_sit": None,
        }

        if player:
            entry["player"] = {
                "id": player.id,
                "full_name": player.full_name,
                "team": player.team,
                "position": player.position,
                "status": player.status,
            }
            # Today's game info
            if player.team:
                entry["today_game"] = team_games.get(player.team)

            # Latest stats
            if player.id in stats_map:
                entry["stats"] = stats_map[player.id]

            # Start/sit recommendation
            if player.id in start_sit_map:
                entry["start_sit"] = start_sit_map[player.id]

        roster_entries.append(entry)

    return {"league_id": league_id, "date": today, "roster": roster_entries}
