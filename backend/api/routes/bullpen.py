"""Bullpen / reliever usage API routes."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.database.models import (
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
    today = date.today()
    today_str = today.isoformat()

    # Get the most recent classification date (might not be today)
    latest_date_result = await db.execute(
        select(RelieverRole.date).order_by(RelieverRole.date.desc()).limit(1)
    )
    latest_date = latest_date_result.scalar_one_or_none()
    if not latest_date:
        return {"date": today_str, "day_columns": [], "relievers": []}

    # Build reliever roles query
    query = (
        select(RelieverRole, Player)
        .join(Player, RelieverRole.player_id == Player.id)
        .where(RelieverRole.date == latest_date)
    )
    if team:
        query = query.where(Player.team == team)
    if role:
        query = query.where(RelieverRole.role == role)

    query = query.order_by(RelieverRole.role, RelieverRole.confidence.desc())

    result = await db.execute(query)
    rows = result.all()

    # Get user's rostered player IDs
    roster_result = await db.execute(
        select(UserRoster.player_id).where(UserRoster.player_id.isnot(None))
    )
    roster_ids = {row[0] for row in roster_result.all()}

    # Season stats from all non-starter appearances
    season_result = await db.execute(
        select(
            PitcherAppearance.player_id,
            func.count().label("g"),
            func.sum(PitcherAppearance.innings_pitched).label("ip"),
            func.sum(PitcherAppearance.earned_runs).label("er"),
            func.sum(PitcherAppearance.strikeouts).label("k"),
            func.sum(PitcherAppearance.walks).label("bb"),
            func.sum(PitcherAppearance.hits_allowed).label("h"),
            func.sum(PitcherAppearance.save).label("sv"),
            func.sum(PitcherAppearance.hold).label("hld"),
        )
        .where(PitcherAppearance.is_starter == 0)
        .group_by(PitcherAppearance.player_id)
    )
    season_stats: dict[int, dict] = {}
    for row in season_result.all():
        ip = row.ip or 0.0
        k = row.k or 0
        bb = row.bb or 0
        h = row.h or 0
        er = row.er or 0
        denom = k + bb + h
        season_stats[row.player_id] = {
            "g": row.g,
            "ip": round(ip, 1),
            "era": round((er / ip) * 9, 2) if ip > 0 else 0.0,
            "sv": row.sv or 0,
            "hld": row.hld or 0,
            "k9": round((k / ip) * 9, 2) if ip > 0 else 0.0,
            "k_pct": round(k / denom, 3) if denom > 0 else 0.0,
        }

    # Daily pitches for last 7 days
    day_columns = [(today - timedelta(days=i)).isoformat() for i in range(7)]

    daily_result = await db.execute(
        select(
            PitcherAppearance.player_id,
            PitcherAppearance.date,
            PitcherAppearance.pitches,
        ).where(
            PitcherAppearance.is_starter == 0,
            PitcherAppearance.date >= day_columns[-1],
        )
    )
    daily_by_player: dict[int, dict[str, int]] = {}
    for row in daily_result.all():
        if row.player_id not in daily_by_player:
            daily_by_player[row.player_id] = {}
        daily_by_player[row.player_id][row.date] = row.pitches

    # Build response
    relievers = []
    for rr, player in rows:
        is_rostered = player.id in roster_ids
        if roster_only and not is_rostered:
            continue

        pid = player.id
        stats = season_stats.get(pid, {})
        daily = daily_by_player.get(pid, {})

        relievers.append({
            "player_id": pid,
            "full_name": player.full_name,
            "team": player.team,
            "throws": player.throws,
            "is_rostered": is_rostered,
            "role": rr.role,
            "confidence": rr.confidence,
            "available_tonight": bool(rr.available_tonight),
            "season_g": stats.get("g", 0),
            "season_ip": stats.get("ip", 0.0),
            "season_era": stats.get("era", 0.0),
            "season_sv": stats.get("sv", 0),
            "season_hld": stats.get("hld", 0),
            "season_k9": stats.get("k9", 0.0),
            "season_k_pct": stats.get("k_pct", 0.0),
            "daily_pitches": [daily.get(d) for d in day_columns],
            "pitches_last_3d": rr.pitches_last_3d,
            "pitches_last_7d": rr.pitches_last_7d,
            "days_since_last_appearance": rr.days_since_last_appearance,
        })

    return {"date": latest_date, "day_columns": day_columns, "relievers": relievers}
