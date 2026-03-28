"""FanGraphs CSV leaderboard fetcher."""

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

# FanGraphs CSV export URLs — page=1_10000 fetches all players at once
FANGRAPHS_BATTING_URL = (
    "{base}/leaders/major-league"
    "?pos=all&stats=bat&lg=all&type=8&season={year}&month=0"
    "&ind=0&page=1_10000&exportCSV=1"
)

FANGRAPHS_PITCHING_URL = (
    "{base}/leaders/major-league"
    "?pos=all&stats=pit&lg=all&type=8&season={year}&month=0"
    "&ind=0&page=1_10000&exportCSV=1"
)

FANGRAPHS_PROJECTIONS_URL = (
    "{base}/leaders/major-league"
    "?pos=all&stats={stats}&lg=all&type=8&season={year}&month=0"
    "&ind=0&page=1_10000&projections=rfangraphsdc&exportCSV=1"
)


async def _fetch_csv(client: httpx.AsyncClient, url: str) -> pd.DataFrame | None:
    """Download a CSV from FanGraphs and return as DataFrame."""
    try:
        resp = await client.get(
            url,
            timeout=60.0,
            headers={"User-Agent": "RipkenDashboard/0.1"},
            follow_redirects=True,
        )
        resp.raise_for_status()
        text = resp.text
        # FanGraphs sometimes wraps CSV in HTML; detect and skip
        if "<html" in text.lower()[:200]:
            print("  Got HTML instead of CSV — FanGraphs may be blocking")
            return None
        return pd.read_csv(StringIO(text))
    except Exception as e:
        print(f"  Error fetching FanGraphs CSV: {e}")
        return None


async def _build_fg_id_map(db: AsyncSession) -> dict[int, int]:
    """Map fangraphs_id -> internal player id."""
    result = await db.execute(
        select(Player.id, Player.fangraphs_id).where(Player.fangraphs_id.isnot(None))
    )
    return {row.fangraphs_id: row.id for row in result.all()}


async def _store_stats(
    db: AsyncSession,
    df: pd.DataFrame,
    stat_type: str,
    fg_id_map: dict[int, int],
    today: str,
) -> int:
    """Store DataFrame rows as PlayerStats JSON blobs. Returns count stored."""
    # FanGraphs CSV uses "playerid" column for FanGraphs ID
    id_col = None
    for candidate in ["playerid", "PlayerId", "xMLBAMID"]:
        if candidate in df.columns:
            id_col = candidate
            break

    if id_col is None:
        print(f"  Could not find player ID column in FanGraphs CSV. Columns: {list(df.columns)}")
        return 0

    count = 0
    for _, row in df.iterrows():
        fg_id = row.get(id_col)
        if pd.isna(fg_id):
            continue
        try:
            fg_id = int(fg_id)
        except (ValueError, TypeError):
            continue

        player_id = fg_id_map.get(fg_id)
        if player_id is None:
            continue

        stats_dict = {
            k: (None if pd.isna(v) else v)
            for k, v in row.to_dict().items()
            if k != id_col
        }

        stmt = sqlite_insert(PlayerStats).values(
            player_id=player_id,
            date=today,
            source="fangraphs",
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


async def sync_fangraphs_stats(db: AsyncSession) -> None:
    """Fetch FanGraphs batting and pitching leaderboards, store in player_stats."""
    year = date.today().year
    today = date.today().isoformat()
    base = settings.fangraphs_base_url

    print(f"Syncing FanGraphs stats for {year}...")
    fg_id_map = await _build_fg_id_map(db)
    print(f"  Loaded {len(fg_id_map)} FanGraphs ID mappings")

    async with httpx.AsyncClient() as client:
        batting_url = FANGRAPHS_BATTING_URL.format(base=base, year=year)
        batting_df = await _fetch_csv(client, batting_url)
        await asyncio.sleep(3)

        pitching_url = FANGRAPHS_PITCHING_URL.format(base=base, year=year)
        pitching_df = await _fetch_csv(client, pitching_url)

    if batting_df is not None and not batting_df.empty:
        n = await _store_stats(db, batting_df, "batting", fg_id_map, today)
        print(f"  Stored {n} FanGraphs batting rows")
    else:
        print("  No FanGraphs batting data fetched")

    if pitching_df is not None and not pitching_df.empty:
        n = await _store_stats(db, pitching_df, "pitching", fg_id_map, today)
        print(f"  Stored {n} FanGraphs pitching rows")
    else:
        print("  No FanGraphs pitching data fetched")

    print("FanGraphs sync complete.")


async def sync_fangraphs_projections(db: AsyncSession) -> None:
    """Fetch ROS projections (Steamer/ZiPS) from FanGraphs."""
    year = date.today().year
    today = date.today().isoformat()
    base = settings.fangraphs_base_url

    print(f"Syncing FanGraphs projections for {year}...")
    fg_id_map = await _build_fg_id_map(db)

    async with httpx.AsyncClient() as client:
        for stats_type in ("bat", "pit"):
            url = FANGRAPHS_PROJECTIONS_URL.format(base=base, year=year, stats=stats_type)
            df = await _fetch_csv(client, url)
            if df is not None and not df.empty:
                stat_label = f"projections_{'batting' if stats_type == 'bat' else 'pitching'}"
                n = await _store_stats(db, df, stat_label, fg_id_map, today)
                print(f"  Stored {n} FanGraphs {stat_label} projection rows")
            await asyncio.sleep(3)

    print("FanGraphs projections sync complete.")


async def sync_projections_from_csv(db: AsyncSession) -> None:
    """Load ROS projections from local CSV files in data/projections/."""
    import os

    today = date.today().isoformat()
    base_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "projections")
    )

    # Build both ID maps for matching
    fg_id_map = await _build_fg_id_map(db)

    result = await db.execute(
        select(Player.id, Player.mlb_id).where(Player.mlb_id.isnot(None))
    )
    mlb_id_map = {row.mlb_id: row.id for row in result.all()}

    for csv_name, stat_type in [
        ("batting.csv", "projections_batting"),
        ("pitching.csv", "projections_pitching"),
    ]:
        path = os.path.join(base_dir, csv_name)
        if not os.path.exists(path):
            print(f"  Skipping {csv_name} — file not found at {path}")
            continue

        df = pd.read_csv(path)
        print(f"  Loaded {len(df)} rows from {csv_name}")

        count = 0
        for _, row in df.iterrows():
            player_id = None

            # Try MLBAMID -> mlb_id first
            mlbam = row.get("MLBAMID")
            if pd.notna(mlbam):
                player_id = mlb_id_map.get(int(mlbam))

            # Fallback: PlayerId -> fangraphs_id
            if player_id is None:
                fg_id = row.get("playerid") or row.get("PlayerId")
                if fg_id is not None and pd.notna(fg_id):
                    try:
                        player_id = fg_id_map.get(int(fg_id))
                    except (ValueError, TypeError):
                        pass

            if player_id is None:
                continue

            stats_dict = {
                k: (None if pd.isna(v) else v)
                for k, v in row.to_dict().items()
                if k not in ("playerid", "PlayerId", "MLBAMID")
            }

            stmt = sqlite_insert(PlayerStats).values(
                player_id=player_id,
                date=today,
                source="fangraphs",
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
        print(f"  Stored {count} {stat_type} projection rows")

    print("CSV projections import complete.")


if __name__ == "__main__":
    import argparse

    from backend.database.connection import async_session

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--action",
        choices=["stats", "projections", "projections-csv"],
        default="stats",
        help="Which data to fetch",
    )
    args = parser.parse_args()

    async def main():
        async with async_session() as db:
            if args.action == "stats":
                await sync_fangraphs_stats(db)
            elif args.action == "projections":
                await sync_fangraphs_projections(db)
            elif args.action == "projections-csv":
                await sync_projections_from_csv(db)

    asyncio.run(main())
