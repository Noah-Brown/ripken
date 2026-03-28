"""Team analysis API route — category strengths, weaknesses, and needs."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.analytics.category_value import get_team_analysis
from backend.database.models import LeagueTeam
from backend.yahoo.client import get_matchup

router = APIRouter(prefix="/api", tags=["team-analysis"])
logger = logging.getLogger(__name__)


@router.get("/leagues/{league_id}/team-analysis")
async def team_analysis(
    league_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """Get category analysis for the user's team in a league."""
    result = await get_team_analysis(db, league_id)
    if "error" in result:
        return result

    # Populate current_matchup for H2H leagues
    if result.get("league_format") == "head":
        try:
            team_result = await db.execute(
                select(LeagueTeam).where(
                    LeagueTeam.league_id == league_id,
                    LeagueTeam.is_current_user == 1,
                )
            )
            my_team = team_result.scalar_one_or_none()
            if my_team:
                matchup_data = await get_matchup(db, my_team.yahoo_team_key)
                matchups = matchup_data.get("matchups", {})
                if isinstance(matchups, dict):
                    matchup_list = matchups.get("matchup", [])
                    if isinstance(matchup_list, list) and matchup_list:
                        current = matchup_list[-1]
                        teams = current.get("teams", {}).get("team", [])
                        for team in teams if isinstance(teams, list) else []:
                            team_info = team[0] if isinstance(team, list) and team else team
                            if isinstance(team_info, dict):
                                name = team_info.get("name", "")
                                if name and name != my_team.team_name:
                                    result["current_matchup"] = {
                                        "opponent": name,
                                        "category_comparison": [],
                                    }
        except Exception:
            logger.warning("Failed to fetch H2H matchup data", exc_info=True)

    return result
