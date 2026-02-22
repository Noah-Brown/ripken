from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.database.models import Game, Player, ProbablePitcher

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/today")
async def get_today(db: AsyncSession = Depends(get_db_session)):
    """Today's games with probable pitchers."""
    today = date.today().isoformat()

    games_result = await db.execute(
        select(Game).where(Game.date == today).order_by(Game.game_time)
    )
    games = games_result.scalars().all()

    response = []
    for game in games:
        # Fetch probable pitchers for this game
        pp_result = await db.execute(
            select(ProbablePitcher, Player)
            .join(Player, ProbablePitcher.player_id == Player.id)
            .where(ProbablePitcher.game_id == game.id)
        )
        pitchers = pp_result.all()

        pitcher_map = {}
        for pp, player in pitchers:
            pitcher_map[pp.team] = {
                "name": player.full_name,
                "mlb_id": player.mlb_id,
                "team": pp.team,
                "is_confirmed": bool(pp.is_confirmed),
            }

        response.append({
            "game_id": game.id,
            "date": game.date,
            "game_time": game.game_time,
            "home_team": game.home_team,
            "away_team": game.away_team,
            "status": game.status,
            "home_score": game.home_score,
            "away_score": game.away_score,
            "venue": game.venue,
            "probable_pitchers": {
                "home": pitcher_map.get(game.home_team),
                "away": pitcher_map.get(game.away_team),
            },
        })

    return {"date": today, "games": response}
