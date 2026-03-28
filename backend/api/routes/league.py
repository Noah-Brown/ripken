"""League-wide roster API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.database.models import LeagueRoster, LeagueTeam, Player, UserLeague

router = APIRouter(prefix="/api", tags=["league"])

POSITION_ORDER = [
    "C", "1B", "2B", "SS", "3B", "OF", "Util",
    "SP", "RP", "BN", "DL", "IL", "IL+", "NA",
]


@router.get("/league/{league_id}/rosters")
async def get_league_rosters(
    league_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """All rostered players in a league, grouped by position."""
    # Get league info
    league_result = await db.execute(
        select(UserLeague).where(UserLeague.id == league_id)
    )
    league = league_result.scalar_one_or_none()
    if not league:
        return {"error": "League not found"}

    # Get teams
    teams_result = await db.execute(
        select(LeagueTeam).where(LeagueTeam.league_id == league_id)
    )
    teams = [
        {
            "yahoo_team_key": t.yahoo_team_key,
            "team_name": t.team_name,
            "is_current_user": bool(t.is_current_user),
        }
        for t in teams_result.scalars().all()
    ]

    # Build user team keys for highlighting
    user_team_keys = {t["yahoo_team_key"] for t in teams if t["is_current_user"]}

    # Get all roster entries with player data
    roster_result = await db.execute(
        select(LeagueRoster, Player)
        .outerjoin(Player, LeagueRoster.player_id == Player.id)
        .where(LeagueRoster.league_id == league_id)
        .order_by(LeagueRoster.roster_position, LeagueRoster.yahoo_player_name)
    )

    # Group by position
    positions: dict[str, list] = {}
    for lr, player in roster_result.all():
        pos = lr.roster_position or "BN"
        if pos not in positions:
            positions[pos] = []
        positions[pos].append({
            "player_id": player.id if player else None,
            "player_name": player.full_name if player else lr.yahoo_player_name,
            "team": player.team if player else None,
            "owner": lr.yahoo_team_name,
            "is_current_user": lr.yahoo_team_key in user_team_keys,
        })

    # Sort positions by defined order
    ordered: dict[str, list] = {}
    for pos in POSITION_ORDER:
        if pos in positions:
            ordered[pos] = positions[pos]
    for pos in positions:
        if pos not in ordered:
            ordered[pos] = positions[pos]

    return {
        "league_name": league.league_name,
        "teams": teams,
        "positions": ordered,
    }
