"""Waiver wire scoring and ranking engine.

Ranks available free agents by pickup value for each league,
considering projections, recent performance, and league format.
"""

import json
import logging
from datetime import date, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import Player, PlayerStats, UserLeague, UserRoster

logger = logging.getLogger(__name__)


async def score_free_agents(
    db: AsyncSession,
    league_id: int,
    position: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Score and rank free agents for a given league.

    Returns a list of scored players, sorted by pickup value.
    """
    # Get league info for format-specific scoring
    league_result = await db.execute(
        select(UserLeague).where(UserLeague.id == league_id)
    )
    league = league_result.scalar_one_or_none()
    if not league:
        return []

    # Get rostered player IDs across all leagues
    roster_result = await db.execute(
        select(UserRoster.player_id).where(UserRoster.player_id.isnot(None))
    )
    roster_ids = {row[0] for row in roster_result.all()}

    # Get all active players not on roster
    query = select(Player).where(
        Player.status == "active",
        Player.id.notin_(roster_ids) if roster_ids else True,
    )
    if position:
        query = query.where(Player.position == position)

    result = await db.execute(query)
    free_agents = result.scalars().all()

    if not free_agents:
        return []

    fa_ids = [p.id for p in free_agents]

    # Batch load projections
    projections = await _load_projections(db, fa_ids)

    # Batch load recent stats (last 14 days)
    recent = await _load_recent_stats(db, fa_ids)

    # Score each free agent
    scored = []
    league_format = league.format or "head"

    for player in free_agents:
        proj = projections.get(player.id)
        rec = recent.get(player.id)

        score, breakdown = _compute_score(player, proj, rec, league_format)

        if score <= 0:
            continue

        scored.append({
            "player_id": player.id,
            "full_name": player.full_name,
            "team": player.team,
            "position": player.position,
            "status": player.status,
            "score": round(score, 1),
            "breakdown": breakdown,
            "projection": _summarize_stats(proj),
            "recent": _summarize_stats(rec),
        })

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def _compute_score(
    player: Player,
    projection: dict | None,
    recent: dict | None,
    league_format: str,
) -> tuple[float, dict]:
    """Compute a pickup value score for a free agent."""
    score = 0.0
    breakdown = {}

    # Projection-based value (50% weight)
    proj_score = 0.0
    if projection:
        if player.position in ("SP", "RP", "P"):
            proj_score = _score_pitcher_projection(projection)
        else:
            proj_score = _score_hitter_projection(projection)
    breakdown["projection"] = round(proj_score, 1)
    score += proj_score * 0.50

    # Recent performance / hot streak (35% weight)
    recent_score = 0.0
    if recent:
        if player.position in ("SP", "RP", "P"):
            recent_score = _score_pitcher_recent(recent)
        else:
            recent_score = _score_hitter_recent(recent)
    breakdown["recent"] = round(recent_score, 1)
    score += recent_score * 0.35

    # Positional scarcity bonus (15% weight)
    scarcity = _positional_scarcity(player.position)
    breakdown["scarcity"] = round(scarcity, 1)
    score += scarcity * 0.15

    return score, breakdown


def _score_hitter_projection(stats: dict) -> float:
    """Score a hitter based on ROS projections."""
    score = 0.0
    # wRC+ is the best single-number hitter metric
    wrc_plus = _get_num(stats, "wRC+", "wrc_plus")
    if wrc_plus is not None:
        score += max(0, (wrc_plus - 80) * 1.5)  # 100 wRC+ → 30 pts

    # HR upside
    hr = _get_num(stats, "HR", "hr")
    if hr is not None:
        score += hr * 2

    # SB value
    sb = _get_num(stats, "SB", "sb")
    if sb is not None:
        score += sb * 3

    # OBP / OPS
    ops = _get_num(stats, "OPS", "ops")
    if ops is not None:
        score += max(0, (ops - 0.650) * 100)

    return min(score, 100)


def _score_pitcher_projection(stats: dict) -> float:
    """Score a pitcher based on ROS projections."""
    score = 50.0  # Start neutral
    era = _get_num(stats, "ERA", "era")
    if era is not None:
        score += max(0, (4.50 - era) * 15)  # Lower ERA = higher score

    whip = _get_num(stats, "WHIP", "whip")
    if whip is not None:
        score += max(0, (1.40 - whip) * 30)

    k9 = _get_num(stats, "K/9", "k_per_9", "SO9")
    if k9 is not None:
        score += max(0, (k9 - 6) * 5)

    return min(max(score, 0), 100)


def _score_hitter_recent(stats: dict) -> float:
    """Score a hitter on recent (L14D) performance for hot streak detection."""
    score = 0.0
    wrc_plus = _get_num(stats, "wRC+", "wrc_plus")
    if wrc_plus is not None:
        if wrc_plus > 140:
            score += 40  # Hot streak bonus
        elif wrc_plus > 120:
            score += 25
        elif wrc_plus > 100:
            score += 15

    ops = _get_num(stats, "OPS", "ops")
    if ops is not None and ops > 0.900:
        score += 20

    avg = _get_num(stats, "AVG", "avg")
    if avg is not None and avg > 0.300:
        score += 15

    return min(score, 100)


def _score_pitcher_recent(stats: dict) -> float:
    """Score a pitcher on recent performance."""
    score = 50.0
    era = _get_num(stats, "ERA", "era")
    if era is not None:
        if era < 2.50:
            score += 30
        elif era < 3.50:
            score += 20
        elif era < 4.50:
            score += 10

    whip = _get_num(stats, "WHIP", "whip")
    if whip is not None and whip < 1.10:
        score += 20

    return min(max(score, 0), 100)


def _positional_scarcity(position: str | None) -> float:
    """Bonus for scarce positions."""
    scarcity_map = {
        "C": 25, "SS": 15, "2B": 10, "3B": 10,
        "SP": 5, "RP": 15,  # Closers are scarce
        "1B": 0, "OF": 0, "LF": 0, "CF": 0, "RF": 0, "DH": 0,
    }
    return scarcity_map.get(position or "", 5)


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


def _summarize_stats(stats: dict | None) -> dict | None:
    """Extract key stats for display."""
    if not stats:
        return None
    # Return the raw stats dict - frontend picks what to display
    return stats


async def _load_projections(
    db: AsyncSession, player_ids: list[int]
) -> dict[int, dict]:
    """Load FanGraphs ROS projections for a batch of players."""
    if not player_ids:
        return {}

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
    return projections


async def _load_recent_stats(
    db: AsyncSession, player_ids: list[int]
) -> dict[int, dict]:
    """Load most recent FanGraphs stats for a batch of players."""
    if not player_ids:
        return {}

    result = await db.execute(
        select(PlayerStats)
        .where(
            PlayerStats.player_id.in_(player_ids),
            PlayerStats.source == "fangraphs",
            PlayerStats.stat_type.in_(["batting", "pitching"]),
        )
        .order_by(PlayerStats.date.desc())
    )

    recent: dict[int, dict] = {}
    for stat in result.scalars().all():
        if stat.player_id not in recent:
            try:
                recent[stat.player_id] = json.loads(stat.stats)
            except (json.JSONDecodeError, TypeError):
                pass
    return recent
