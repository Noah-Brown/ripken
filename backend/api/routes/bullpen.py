"""Bullpen / reliever usage API routes."""

import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.database.models import (
    Game,
    PitcherAppearance,
    Player,
    RelieverRole,
    UserRoster,
)

router = APIRouter(prefix="/api", tags=["bullpen"])


@router.get("/bullpen")
async def get_bullpen(
    team: str | None = Query(None, description="Filter by MLB team"),
    role: str | None = Query(None, description="Filter by role"),
    roster_only: bool = Query(False, description="Only show rostered relievers"),
    db: AsyncSession = Depends(get_db_session),
):
    """All classified relievers with usage data and availability."""
    today = date.today().isoformat()

    # Get the most recent classification date (might not be today)
    latest_date_result = await db.execute(
        select(RelieverRole.date).order_by(RelieverRole.date.desc()).limit(1)
    )
    latest_date = latest_date_result.scalar_one_or_none()
    if not latest_date:
        return {"date": today, "relievers": []}

    # Build query
    query = (
        select(RelieverRole, Player)
        .join(Player, RelieverRole.player_id == Player.id)
        .where(RelieverRole.date == latest_date)
    )
    if team:
        query = query.where(Player.team == team)
    if role:
        query = query.where(RelieverRole.role == role)

    query = query.order_by(
        # Sort: closer > setup > middle > long > mop_up
        RelieverRole.role,
        RelieverRole.confidence.desc(),
    )

    result = await db.execute(query)
    rows = result.all()

    # Get user's rostered player IDs for annotation
    roster_result = await db.execute(
        select(UserRoster.player_id).where(UserRoster.player_id.isnot(None))
    )
    roster_ids = {row[0] for row in roster_result.all()}

    # Get 14-day usage heatmap data
    heatmap_start = (date.today() - timedelta(days=14)).isoformat()
    appearances_result = await db.execute(
        select(PitcherAppearance)
        .where(PitcherAppearance.date >= heatmap_start)
        .order_by(PitcherAppearance.date)
    )
    appearances_by_player: dict[int, list[dict]] = {}
    for pa in appearances_result.scalars().all():
        if pa.player_id not in appearances_by_player:
            appearances_by_player[pa.player_id] = []
        appearances_by_player[pa.player_id].append({
            "date": pa.date,
            "innings_pitched": pa.innings_pitched,
            "pitches": pa.pitches,
            "earned_runs": pa.earned_runs,
            "strikeouts": pa.strikeouts,
            "save": pa.save,
            "hold": pa.hold,
            "blown_save": pa.blown_save,
        })

    relievers = []
    for rr, player in rows:
        is_rostered = player.id in roster_ids
        if roster_only and not is_rostered:
            continue

        evidence = {}
        if rr.role_evidence:
            try:
                evidence = json.loads(rr.role_evidence)
            except (json.JSONDecodeError, TypeError):
                pass

        relievers.append({
            "player_id": player.id,
            "full_name": player.full_name,
            "team": player.team,
            "throws": player.throws,
            "is_rostered": is_rostered,
            "role": rr.role,
            "confidence": rr.confidence,
            "available_tonight": bool(rr.available_tonight),
            "saves_last_14d": rr.saves_last_14d,
            "holds_last_14d": rr.holds_last_14d,
            "appearances_last_7d": rr.appearances_last_7d,
            "avg_leverage_last_14d": rr.avg_leverage_last_14d,
            "days_since_last_appearance": rr.days_since_last_appearance,
            "pitches_last_3d": rr.pitches_last_3d,
            "pitches_last_7d": rr.pitches_last_7d,
            "evidence": evidence,
            "usage_heatmap": appearances_by_player.get(player.id, []),
        })

    return {"date": latest_date, "relievers": relievers}
