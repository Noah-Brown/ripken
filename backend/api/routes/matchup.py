"""Matchup projection API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.analytics.matchup import project_matchup

router = APIRouter(prefix="/api", tags=["matchup"])


@router.get("/matchup/{league_id}")
async def get_matchup(league_id: int, db: AsyncSession = Depends(get_db_session)):
    """Projected category outcomes for the current H2H matchup week."""
    return await project_matchup(db, league_id)
