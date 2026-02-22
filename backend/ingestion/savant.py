"""Baseball Savant / Statcast CSV leaderboard fetcher."""

import asyncio
import json
from datetime import date
from io import StringIO

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database.models import Player, PlayerStats

# Statcast leaderboard CSV export URLs
SAVANT_BATTING_URL = (
    "{base}/leaderboard/custom"
    "?year={year}&type=batter&filter=&min=q&selections="
    "xba,xslg,xwoba,xobp,xiso,exit_velocity_avg,launch_angle_avg,"
    "barrel_batted_rate,hard_hit_percent,sprint_speed,whiff_percent"
    "&chart=false&x=xba&y=xba&r=no&chartType=beeswarm&csv=true"
)

SAVANT_PITCHING_URL = (
    "{base}/leaderboard/custom"
    "?year={year}&type=pitcher&filter=&min=q&selections="
    "xba,xslg,xwoba,xera,exit_velocity_avg,launch_angle_avg,"
    "barrel_batted_rate,hard_hit_percent,whiff_percent,k_percent,bb_percent"
    "&chart=false&x=xba&y=xba&r=no&chartType=beeswarm&csv=true"
)


async def _fetch_csv(client: httpx.AsyncClient, url: str) -> pd.DataFrame | None:
    """Download a CSV from Baseball Savant and return as DataFrame."""
    try:
        resp = await client.get(url, timeout=60.0)
        resp.raise_for_status()
        return pd.read_csv(StringIO(resp.text))
    except Exception as e:
        print(f"  Error fetching Savant CSV: {e}")
        return None


async def _build_mlb_id_map(db: AsyncSession) -> dict[int, int]:
    """Map mlb_id -> internal player id."""
    result = await db.execute(
        select(Player.id, Player.mlb_id).where(Player.mlb_id.isnot(None))
    )
    return {row.mlb_id: row.id for row in result.all()}


async def _store_stats(
    db: AsyncSession,
    df: pd.DataFrame,
    stat_type: str,
    id_column: str,
    mlb_id_map: dict[int, int],
    today: str,
) -> int:
    """Store DataFrame rows as PlayerStats JSON blobs. Returns count stored."""
    count = 0
    for _, row in df.iterrows():
        mlb_id = row.get(id_column)
        if pd.isna(mlb_id):
            continue
        mlb_id = int(mlb_id)
        player_id = mlb_id_map.get(mlb_id)
        if player_id is None:
            continue

        stats_dict = {
            k: (None if pd.isna(v) else v)
            for k, v in row.to_dict().items()
            if k != id_column
        }

        stmt = sqlite_insert(PlayerStats).values(
            player_id=player_id,
            date=today,
            source="savant",
            stat_type=stat_type,
            stats=json.dumps(stats_dict),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["player_id", "date", "source", "stat_type"],
            set_={"stats": stmt.excluded.stats},
        )
        await db.execute(stmt)
        count += 1

    await db.commit()
    return count


async def sync_savant_stats(db: AsyncSession) -> None:
    """Fetch Statcast batting and pitching leaderboards, store in player_stats."""
    year = date.today().year
    today = date.today().isoformat()
    base = settings.savant_base_url

    print(f"Syncing Savant stats for {year}...")
    mlb_id_map = await _build_mlb_id_map(db)
    print(f"  Loaded {len(mlb_id_map)} player ID mappings")

    async with httpx.AsyncClient() as client:
        batting_url = SAVANT_BATTING_URL.format(base=base, year=year)
        pitching_url = SAVANT_PITCHING_URL.format(base=base, year=year)

        batting_df = await _fetch_csv(client, batting_url)
        await asyncio.sleep(2)  # Be respectful
        pitching_df = await _fetch_csv(client, pitching_url)

    if batting_df is not None and not batting_df.empty:
        n = await _store_stats(db, batting_df, "savant_batting", "player_id", mlb_id_map, today)
        print(f"  Stored {n} Savant batting rows")
    else:
        print("  No Savant batting data fetched")

    if pitching_df is not None and not pitching_df.empty:
        n = await _store_stats(db, pitching_df, "savant_pitching", "player_id", mlb_id_map, today)
        print(f"  Stored {n} Savant pitching rows")
    else:
        print("  No Savant pitching data fetched")

    print("Savant sync complete.")


if __name__ == "__main__":
    from backend.database.connection import async_session

    async def main():
        async with async_session() as db:
            await sync_savant_stats(db)

    asyncio.run(main())
