"""Reliever role inference engine.

Classifies every reliever as closer / setup / middle / long / mop_up
with a confidence level, and estimates nightly availability.
"""

import json
import logging
from datetime import date, timedelta

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import PitcherAppearance, Player, RelieverRole

logger = logging.getLogger(__name__)

# Minimum appearances in 14 days to classify
MIN_APPEARANCES = 1


async def compute_reliever_roles(db: AsyncSession) -> int:
    """Run the reliever role classification algorithm.

    Analyzes pitcher appearances over the trailing 14-day window and
    classifies each reliever's role. Stores results in reliever_roles table.

    Returns the number of relievers classified.
    """
    today = date.today()
    today_str = today.isoformat()
    window_start = (today - timedelta(days=14)).isoformat()
    three_days_ago = (today - timedelta(days=3)).isoformat()
    seven_days_ago = (today - timedelta(days=7)).isoformat()

    # Get all pitcher appearances in the 14-day window
    result = await db.execute(
        select(
            PitcherAppearance.player_id,
            func.count().label("appearances"),
            func.sum(PitcherAppearance.save).label("saves"),
            func.sum(PitcherAppearance.hold).label("holds"),
            func.sum(PitcherAppearance.blown_save).label("blown_saves"),
            func.avg(PitcherAppearance.leverage_index_avg).label("avg_leverage"),
            func.avg(PitcherAppearance.entered_inning).label("avg_inning_entered"),
            func.avg(PitcherAppearance.innings_pitched).label("avg_ip"),
            func.sum(PitcherAppearance.pitches).label("total_pitches"),
            func.max(PitcherAppearance.date).label("last_appearance_date"),
        )
        .where(PitcherAppearance.date >= window_start)
        .group_by(PitcherAppearance.player_id)
        .having(func.count() >= MIN_APPEARANCES)
    )
    pitcher_stats = result.all()

    if not pitcher_stats:
        logger.info("No relievers with enough appearances to classify.")
        return 0

    # Get recent workload data (last 3 and 7 days)
    workload_3d = await _get_workload(db, three_days_ago)
    workload_7d = await _get_workload(db, seven_days_ago)

    # Get 7-day-ago roles for change detection
    seven_days_ago_date = (today - timedelta(days=7)).isoformat()
    old_roles_result = await db.execute(
        select(RelieverRole.player_id, RelieverRole.role)
        .where(RelieverRole.date == seven_days_ago_date)
    )
    old_roles = {row[0]: row[1] for row in old_roles_result.all()}

    # Delete today's existing classifications (idempotent re-run)
    await db.execute(
        delete(RelieverRole).where(RelieverRole.date == today_str)
    )

    classified = 0
    for row in pitcher_stats:
        player_id = row.player_id
        appearances = row.appearances or 0
        saves = row.saves or 0
        holds = row.holds or 0
        blown_saves = row.blown_saves or 0
        avg_leverage = row.avg_leverage or 0.0
        avg_inning = row.avg_inning_entered or 0.0
        avg_ip = row.avg_ip or 0.0
        last_date = row.last_appearance_date or ""

        # Calculate rates
        save_opps = saves + blown_saves
        save_rate = saves / save_opps if save_opps > 0 else 0.0
        hold_rate = holds / appearances if appearances > 0 else 0.0

        # Classify role
        role, confidence = _classify_role(
            saves, save_rate, save_opps, holds, hold_rate,
            avg_leverage, avg_inning, avg_ip, appearances,
        )

        # Calculate days since last appearance
        if last_date:
            try:
                last_d = date.fromisoformat(last_date)
                days_since = (today - last_d).days
            except ValueError:
                days_since = None
        else:
            days_since = None

        # Workload data
        pitches_3d = workload_3d.get(player_id, {}).get("pitches", 0)
        pitches_7d = workload_7d.get(player_id, {}).get("pitches", 0)
        appearances_7d = workload_7d.get(player_id, {}).get("appearances", 0)
        appearances_3d = workload_3d.get(player_id, {}).get("appearances", 0)

        # Availability estimation
        available = _estimate_availability(
            days_since, appearances_3d, pitches_3d
        )

        evidence = {
            "save_rate": round(save_rate, 3),
            "hold_rate": round(hold_rate, 3),
            "avg_leverage": round(avg_leverage, 2),
            "avg_inning_entered": round(avg_inning, 1),
            "avg_ip": round(avg_ip, 2),
            "appearances_14d": appearances,
            "saves_14d": saves,
            "holds_14d": holds,
        }

        reliever = RelieverRole(
            player_id=player_id,
            date=today_str,
            role=role,
            confidence=confidence,
            role_evidence=json.dumps(evidence),
            saves_last_14d=saves,
            holds_last_14d=holds,
            appearances_last_7d=appearances_7d,
            avg_leverage_last_14d=round(avg_leverage, 2) if avg_leverage else None,
            days_since_last_appearance=days_since,
            pitches_last_3d=pitches_3d,
            pitches_last_7d=pitches_7d,
            available_tonight=1 if available else 0,
        )
        db.add(reliever)
        classified += 1

    await db.commit()
    logger.info(f"Classified {classified} relievers.")
    return classified


def _classify_role(
    saves: int,
    save_rate: float,
    save_opps: int,
    holds: int,
    hold_rate: float,
    avg_leverage: float,
    avg_inning: float,
    avg_ip: float,
    appearances: int,
) -> tuple[str, str]:
    """Classify a reliever's role and confidence level."""
    # Closer: high save rate with multiple saves
    if save_rate >= 0.60 and saves >= 2:
        return "closer", "high"
    if save_rate >= 0.30 and saves >= 1 and avg_leverage >= 1.5:
        return "closer", "medium"

    # Setup: high leverage with holds
    if avg_leverage >= 1.3 and hold_rate >= 0.25:
        consistency = "high" if hold_rate >= 0.40 else "medium"
        return "setup", consistency

    # Middle relief
    if avg_leverage >= 0.8 and avg_inning <= 7:
        return "middle", "medium"

    # Long relief
    if avg_inning <= 6 and avg_ip >= 1.5:
        return "long", "medium"

    # Mop up
    return "mop_up", "low"


def _estimate_availability(
    days_since: int | None,
    appearances_3d: int,
    pitches_3d: int,
) -> bool:
    """Estimate whether a reliever is available tonight."""
    if days_since is not None and days_since == 0:
        return False  # Already pitched today
    if appearances_3d >= 3:
        return False  # Needs rest
    if pitches_3d >= 75:
        return False  # High recent workload
    return True


async def _get_workload(
    db: AsyncSession, since_date: str
) -> dict[int, dict]:
    """Get pitch counts and appearances since a given date."""
    result = await db.execute(
        select(
            PitcherAppearance.player_id,
            func.count().label("appearances"),
            func.sum(PitcherAppearance.pitches).label("pitches"),
        )
        .where(PitcherAppearance.date >= since_date)
        .group_by(PitcherAppearance.player_id)
    )
    return {
        row.player_id: {
            "appearances": row.appearances or 0,
            "pitches": row.pitches or 0,
        }
        for row in result.all()
    }
