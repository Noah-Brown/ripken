"""Alerts API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.database.models import Alert

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts")
async def get_alerts(
    unread_only: bool = True,
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session),
):
    """Get alerts, optionally filtered to unread only."""
    query = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if unread_only:
        query = query.where(Alert.is_read == 0)

    result = await db.execute(query)
    alerts = result.scalars().all()

    return {
        "alerts": [
            {
                "id": a.id,
                "player_id": a.player_id,
                "alert_type": a.alert_type,
                "message": a.message,
                "is_read": bool(a.is_read),
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts
        ],
        "unread_count": len([a for a in alerts if not a.is_read]),
    }


@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(alert_id: int, db: AsyncSession = Depends(get_db_session)):
    """Mark an alert as read."""
    await db.execute(
        update(Alert).where(Alert.id == alert_id).values(is_read=1)
    )
    await db.commit()
    return {"id": alert_id, "is_read": True}


@router.post("/alerts/read-all")
async def mark_all_read(db: AsyncSession = Depends(get_db_session)):
    """Mark all alerts as read."""
    await db.execute(
        update(Alert).where(Alert.is_read == 0).values(is_read=1)
    )
    await db.commit()
    return {"marked_all_read": True}
