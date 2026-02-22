"""Waiver wire API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.analytics.waiver_wire import score_free_agents
from backend.database.models import UserLeague

router = APIRouter(prefix="/api", tags=["waivers"])


@router.get("/waivers/{league_id}")
async def get_waivers(
    league_id: int,
    position: str | None = Query(None, description="Filter by position"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    """Scored and ranked free agents for a league."""
    # Verify league exists
    result = await db.execute(select(UserLeague).where(UserLeague.id == league_id))
    league = result.scalar_one_or_none()
    if not league:
        return {"league_id": league_id, "error": "League not found", "players": []}

    players = await score_free_agents(db, league_id, position=position, limit=limit)

    return {
        "league_id": league_id,
        "league_name": league.league_name,
        "format": league.format,
        "players": players,
    }
