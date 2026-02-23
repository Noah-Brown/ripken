"""H2H matchup projection engine.

Projects each scoring category for the week and identifies
swing categories (close margins, targetable or at risk).
"""

import json
import logging
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import (
    Game,
    Player,
    PlayerStats,
    UserLeague,
    UserRoster,
)

logger = logging.getLogger(__name__)

# Standard H2H categories
BATTING_CATEGORIES = ["R", "HR", "RBI", "SB", "AVG", "OBP", "OPS"]
PITCHING_CATEGORIES = ["W", "K", "ERA", "WHIP", "SV"]
COUNTING_STATS = {"R", "HR", "RBI", "SB", "W", "K", "SV"}
RATE_STATS = {"AVG", "OBP", "OPS", "ERA", "WHIP"}
# For rate stats, lower is better for these:
LOWER_IS_BETTER = {"ERA", "WHIP"}


async def project_matchup(
    db: AsyncSession,
    league_id: int,
) -> dict:
    """Project H2H category outcomes for the current matchup week.

    Returns projected totals for user's team and a comparison summary
    with swing categories highlighted.
    """
    # Get league info
    league_result = await db.execute(
        select(UserLeague).where(UserLeague.id == league_id)
    )
    league = league_result.scalar_one_or_none()
    if not league:
        return {"error": "League not found"}

    # Determine this week's date range
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    date_strs = [(monday + timedelta(days=i)).isoformat() for i in range(7)]

    # Count games per team this week
    games_result = await db.execute(
        select(Game).where(Game.date.in_(date_strs))
    )
    games = games_result.scalars().all()

    team_game_counts: dict[str, int] = {}
    for game in games:
        team_game_counts[game.home_team] = team_game_counts.get(game.home_team, 0) + 1
        team_game_counts[game.away_team] = team_game_counts.get(game.away_team, 0) + 1

    # Get user's roster
    roster_result = await db.execute(
        select(UserRoster, Player)
        .join(Player, UserRoster.player_id == Player.id)
        .where(
            UserRoster.league_id == league_id,
            UserRoster.player_id.isnot(None),
        )
    )
    roster_rows = roster_result.all()

    # Separate hitters and pitchers
    hitters = []
    pitchers = []
    player_ids = []
    for roster_entry, player in roster_rows:
        player_ids.append(player.id)
        if player.position in ("SP", "RP", "P"):
            pitchers.append((roster_entry, player))
        else:
            hitters.append((roster_entry, player))

    # Load projections
    projections = await _load_projections(db, player_ids)

    # Project each category for user's team
    my_projections = _project_team(
        hitters, pitchers, projections, team_game_counts
    )

    # Build per-player breakdown
    player_breakdown = []
    for roster_entry, player in roster_rows:
        proj = projections.get(player.id, {})
        games_this_week = team_game_counts.get(player.team or "", 0)
        is_pitcher = player.position in ("SP", "RP", "P")

        player_breakdown.append({
            "player_id": player.id,
            "full_name": player.full_name,
            "team": player.team,
            "position": player.position,
            "roster_position": roster_entry.roster_position,
            "games_this_week": games_this_week,
            "is_pitcher": is_pitcher,
            "projected_stats": _project_player_stats(
                proj, games_this_week, is_pitcher
            ),
        })

    # Build category summary
    categories = []
    all_cats = BATTING_CATEGORIES + PITCHING_CATEGORIES
    for cat in all_cats:
        my_val = my_projections.get(cat, 0)
        categories.append({
            "category": cat,
            "my_projected": round(my_val, 3) if cat in RATE_STATS else round(my_val, 1),
            "is_counting": cat in COUNTING_STATS,
            "lower_is_better": cat in LOWER_IS_BETTER,
        })

    return {
        "league_id": league_id,
        "league_name": league.league_name,
        "week_start": monday.isoformat(),
        "week_end": sunday.isoformat(),
        "categories": categories,
        "players": player_breakdown,
        "team_games_this_week": team_game_counts,
    }


def _project_team(
    hitters: list,
    pitchers: list,
    projections: dict[int, dict],
    team_game_counts: dict[str, int],
) -> dict[str, float]:
    """Project team totals across all categories."""
    totals: dict[str, float] = {}

    # Hitter counting stats
    total_ab = 0.0
    total_h = 0.0
    total_ob = 0.0  # For OBP
    total_pa = 0.0
    total_tb = 0.0  # For OPS/SLG

    for roster_entry, player in hitters:
        proj = projections.get(player.id, {})
        games = team_game_counts.get(player.team or "", 0)
        if games == 0:
            continue

        # Per-game rates from season/projection stats
        # Assume ~4 PA per game
        pa_per_game = 4.0
        total_pa_proj = pa_per_game * games

        for cat in ["R", "HR", "RBI", "SB"]:
            rate = _get_per_game_rate(proj, cat)
            totals[cat] = totals.get(cat, 0) + rate * games

        # For AVG/OBP/OPS we need to accumulate weighted totals
        avg = _get_num(proj, "AVG", "avg")
        obp = _get_num(proj, "OBP", "obp")
        ops = _get_num(proj, "OPS", "ops")
        ab_proj = total_pa_proj * 0.9  # rough AB from PA

        if avg is not None:
            total_h += avg * ab_proj
            total_ab += ab_proj
        if obp is not None:
            total_ob += obp * total_pa_proj
            total_pa += total_pa_proj
        if ops is not None:
            total_tb += ops * ab_proj  # rough approximation
            if cat == "OPS" and total_ab == 0:
                total_ab = ab_proj

    # Compute rate stats
    if total_ab > 0:
        totals["AVG"] = total_h / total_ab
    if total_pa > 0:
        totals["OBP"] = total_ob / total_pa
    if total_ab > 0:
        totals["OPS"] = total_tb / total_ab

    # Pitcher stats
    total_ip = 0.0
    total_er = 0.0
    total_bb_h = 0.0  # walks + hits for WHIP

    for roster_entry, player in pitchers:
        proj = projections.get(player.id, {})
        games = team_game_counts.get(player.team or "", 0)
        if games == 0:
            continue

        # SPs typically pitch once a week, RPs multiple times
        if player.position == "SP":
            expected_starts = min(games / 5.0, 2.0)  # ~1 start per 5 team games
            ip_per_start = _get_num(proj, "IP", "ip")
            if ip_per_start is not None:
                # IP is season total, estimate per-start
                ip_per_start = ip_per_start / 32.0  # ~32 starts per season
            else:
                ip_per_start = 5.5
            ip_proj = ip_per_start * expected_starts
        else:
            expected_apps = min(games * 0.4, 4.0)
            ip_proj = expected_apps * 1.0

        era = _get_num(proj, "ERA", "era")
        whip = _get_num(proj, "WHIP", "whip")

        if era is not None:
            total_er += (era / 9.0) * ip_proj
        if whip is not None:
            total_bb_h += whip * ip_proj
        total_ip += ip_proj

        for cat in ["W", "K", "SV"]:
            rate = _get_per_game_rate(proj, cat, is_pitcher=True)
            totals[cat] = totals.get(cat, 0) + rate * games

    if total_ip > 0:
        totals["ERA"] = (total_er / total_ip) * 9.0
        totals["WHIP"] = total_bb_h / total_ip

    return totals


def _project_player_stats(
    proj: dict, games: int, is_pitcher: bool
) -> dict[str, float]:
    """Project a single player's stats for the week."""
    result = {}
    if is_pitcher:
        for cat in PITCHING_CATEGORIES:
            if cat in RATE_STATS:
                val = _get_num(proj, cat, cat.lower())
                if val is not None:
                    result[cat] = round(val, 2)
            else:
                rate = _get_per_game_rate(proj, cat, is_pitcher=True)
                result[cat] = round(rate * games, 1)
    else:
        for cat in BATTING_CATEGORIES:
            if cat in RATE_STATS:
                val = _get_num(proj, cat, cat.lower())
                if val is not None:
                    result[cat] = round(val, 3)
            else:
                rate = _get_per_game_rate(proj, cat)
                result[cat] = round(rate * games, 1)
    return result


def _get_per_game_rate(proj: dict, stat: str, is_pitcher: bool = False) -> float:
    """Get a per-game rate for a counting stat from projection data."""
    val = _get_num(proj, stat, stat.lower())
    if val is None:
        return 0.0

    # Season totals — divide by ~150 games for hitters, ~32 starts for SP
    if is_pitcher:
        games_played = _get_num(proj, "G", "g", "GS", "gs")
        if games_played and games_played > 0:
            return val / games_played
        return val / 60.0  # default ~60 appearances
    else:
        games_played = _get_num(proj, "G", "g")
        if games_played and games_played > 0:
            return val / games_played
        return val / 150.0  # default ~150 games


def _get_num(stats: dict, *keys: str) -> float | None:
    """Try multiple key names to find a numeric stat."""
    for key in keys:
        val = stats.get(key)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return None


async def _load_projections(
    db: AsyncSession, player_ids: list[int]
) -> dict[int, dict]:
    """Load ROS projections, falling back to season stats."""
    if not player_ids:
        return {}

    # Try projections first
    result = await db.execute(
        select(PlayerStats)
        .where(
            PlayerStats.player_id.in_(player_ids),
            PlayerStats.source == "fangraphs",
            PlayerStats.stat_type.in_(["projections_batting", "projections_pitching"]),
        )
        .order_by(PlayerStats.date.desc())
    )

    projections: dict[int, dict] = {}
    for stat in result.scalars().all():
        if stat.player_id not in projections:
            try:
                projections[stat.player_id] = json.loads(stat.stats)
            except (json.JSONDecodeError, TypeError):
                pass

    # Fall back to season stats for players without projections
    missing = [pid for pid in player_ids if pid not in projections]
    if missing:
        result = await db.execute(
            select(PlayerStats)
            .where(
                PlayerStats.player_id.in_(missing),
                PlayerStats.source == "fangraphs",
                PlayerStats.stat_type.in_(["batting", "pitching"]),
            )
            .order_by(PlayerStats.date.desc())
        )
        for stat in result.scalars().all():
            if stat.player_id not in projections:
                try:
                    projections[stat.player_id] = json.loads(stat.stats)
                except (json.JSONDecodeError, TypeError):
                    pass

    return projections
