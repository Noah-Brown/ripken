"""Pitching planner API routes."""

import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.database.models import (
    Game,
    Player,
    PlayerStats,
    ProbablePitcher,
    UserLeague,
    UserRoster,
)

router = APIRouter(prefix="/api", tags=["pitching"])


@router.get("/pitching/week")
async def get_pitching_week(db: AsyncSession = Depends(get_db_session)):
    """My starting pitchers mapped to their starts this week with matchup context."""
    today = date.today()
    # Show Mon-Sun of current week
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    date_range = [monday + timedelta(days=i) for i in range(7)]
    date_strs = [d.isoformat() for d in date_range]

    # Get user's rostered pitchers (SPs)
    roster_result = await db.execute(
        select(UserRoster, Player)
        .join(Player, UserRoster.player_id == Player.id)
        .join(UserLeague, UserRoster.league_id == UserLeague.id)
        .where(
            UserRoster.player_id.isnot(None),
            Player.position.in_(["SP", "P"]),
        )
    )
    roster_pitchers = {}
    for roster, player in roster_result.all():
        if player.id not in roster_pitchers:
            roster_pitchers[player.id] = player

    # Get all probable pitchers for the week
    pp_result = await db.execute(
        select(ProbablePitcher, Game, Player)
        .join(Game, ProbablePitcher.game_id == Game.id)
        .join(Player, ProbablePitcher.player_id == Player.id)
        .where(Game.date.in_(date_strs))
        .order_by(Game.date)
    )
    all_starts = pp_result.all()

    # Build schedule: for each of my SPs, when do they pitch this week?
    my_schedule = []
    two_start_ids = set()
    pitcher_starts: dict[int, list] = {}

    for pp, game, player in all_starts:
        if player.id not in pitcher_starts:
            pitcher_starts[player.id] = []
        pitcher_starts[player.id].append({
            "date": game.date,
            "game_id": game.id,
            "opponent": game.away_team if pp.team == game.home_team else game.home_team,
            "home_away": "home" if pp.team == game.home_team else "away",
            "venue": game.venue,
            "is_confirmed": bool(pp.is_confirmed),
        })

    # Identify two-start pitchers
    for pid, starts in pitcher_starts.items():
        if len(starts) >= 2:
            two_start_ids.add(pid)

    # Build my pitchers' week view
    for player_id, player in roster_pitchers.items():
        starts = pitcher_starts.get(player_id, [])

        # Get last 3 starts from pitcher appearances (recent form)
        recent_stats = await _get_recent_pitcher_stats(db, player_id)

        my_schedule.append({
            "player_id": player.id,
            "full_name": player.full_name,
            "team": player.team,
            "throws": player.throws,
            "is_two_start": player_id in two_start_ids,
            "starts": starts,
            "recent_stats": recent_stats,
        })

    # Sort: two-start pitchers first, then by name
    my_schedule.sort(key=lambda x: (not x["is_two_start"], x["full_name"]))

    return {
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "dates": date_strs,
        "pitchers": my_schedule,
    }


@router.get("/pitching/streamers")
async def get_streaming_candidates(db: AsyncSession = Depends(get_db_session)):
    """Best available SP free agents this week by matchup quality."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    date_strs = [(monday + timedelta(days=i)).isoformat() for i in range(7)]

    # Get user's rostered player IDs
    roster_result = await db.execute(
        select(UserRoster.player_id).where(UserRoster.player_id.isnot(None))
    )
    roster_ids = {row[0] for row in roster_result.all()}

    # Get all probable pitchers for the week who are NOT on user's roster
    pp_result = await db.execute(
        select(ProbablePitcher, Game, Player)
        .join(Game, ProbablePitcher.game_id == Game.id)
        .join(Player, ProbablePitcher.player_id == Player.id)
        .where(
            Game.date.in_(date_strs),
            Game.date >= today.isoformat(),
        )
        .order_by(Game.date)
    )

    streamers = []
    seen_players = set()

    for pp, game, player in pp_result.all():
        if player.id in roster_ids:
            continue
        if player.id in seen_players:
            continue
        seen_players.add(player.id)

        # Get pitcher's FanGraphs stats for context
        fg_stats = await _get_fangraphs_pitching_stats(db, player.id)

        opponent = game.away_team if pp.team == game.home_team else game.home_team

        streamers.append({
            "player_id": player.id,
            "full_name": player.full_name,
            "team": player.team,
            "throws": player.throws,
            "date": game.date,
            "opponent": opponent,
            "home_away": "home" if pp.team == game.home_team else "away",
            "venue": game.venue,
            "is_confirmed": bool(pp.is_confirmed),
            "stats": fg_stats,
        })

    return {"streamers": streamers[:30]}


async def _get_recent_pitcher_stats(db: AsyncSession, player_id: int) -> list[dict]:
    """Get a pitcher's last 3 game appearances."""
    from backend.database.models import PitcherAppearance

    result = await db.execute(
        select(PitcherAppearance, Game)
        .join(Game, PitcherAppearance.game_id == Game.id)
        .where(PitcherAppearance.player_id == player_id)
        .order_by(PitcherAppearance.date.desc())
        .limit(3)
    )
    stats = []
    for pa, game in result.all():
        opponent = game.away_team if pa.date == game.date and game.home_team == (
            # Determine opponent from the game
            game.home_team
        ) else game.home_team
        stats.append({
            "date": pa.date,
            "innings_pitched": pa.innings_pitched,
            "earned_runs": pa.earned_runs,
            "strikeouts": pa.strikeouts,
            "walks": pa.walks,
            "hits_allowed": pa.hits_allowed,
            "pitches": pa.pitches,
        })
    return stats


async def _get_fangraphs_pitching_stats(db: AsyncSession, player_id: int) -> dict | None:
    """Get the latest FanGraphs pitching stats for a player."""
    result = await db.execute(
        select(PlayerStats)
        .where(
            PlayerStats.player_id == player_id,
            PlayerStats.source == "fangraphs",
            PlayerStats.stat_type == "pitching",
        )
        .order_by(PlayerStats.date.desc())
        .limit(1)
    )
    stat = result.scalar_one_or_none()
    if stat and stat.stats:
        try:
            return json.loads(stat.stats)
        except (json.JSONDecodeError, TypeError):
            pass
    return None
