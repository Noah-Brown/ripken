"""
Player ID Crosswalk Ingestion
=============================
Downloads the Chadwick Bureau people.csv and populates the `players` table
with cross-referenced IDs (MLB, FanGraphs, Baseball Reference).

Run as:
    python -m backend.ingestion.player_id_crosswalk
"""

import asyncio
import pathlib
from io import StringIO

import httpx
import pandas as pd
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.database.connection import engine, async_session
from backend.database.models import Base, Player

CHADWICK_URL = (
    "https://raw.githubusercontent.com/chadwickbureau/register/master/data/people.csv"
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
LOCAL_CSV_PATH = PROJECT_ROOT / "data" / "chadwick" / "people.csv"

# Players whose last MLB season is >= this year are considered active/recent.
MIN_LAST_PLAYED_YEAR = 2023


async def download_people_csv() -> str:
    """Return the raw CSV text, downloading from GitHub if no local copy exists."""
    if LOCAL_CSV_PATH.exists():
        print(f"Using local copy at {LOCAL_CSV_PATH}")
        return LOCAL_CSV_PATH.read_text(encoding="utf-8")

    print(f"Downloading people.csv from {CHADWICK_URL} ...")
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(CHADWICK_URL)
        resp.raise_for_status()

    csv_text = resp.text
    LOCAL_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_CSV_PATH.write_text(csv_text, encoding="utf-8")
    print(f"Downloaded people.csv ({len(csv_text):,} bytes) -> {LOCAL_CSV_PATH}")
    return csv_text


def parse_and_filter(csv_text: str) -> pd.DataFrame:
    """Parse the Chadwick CSV and filter to active/recent MLB players."""
    df = pd.read_csv(StringIO(csv_text), low_memory=False)

    # key_mlbam must be present (i.e. they have an MLB ID)
    df = df[df["key_mlbam"].notna()]

    # Determine last year played — prefer mlb_played_last, fall back to pro_played_last
    df["_last_year"] = df["mlb_played_last"].fillna(df["pro_played_last"])
    df = df[df["_last_year"].notna()]
    df["_last_year"] = df["_last_year"].astype(int)

    df = df[df["_last_year"] >= MIN_LAST_PLAYED_YEAR]

    print(f"Filtered to {len(df):,} active/recent players")
    return df


def build_player_rows(df: pd.DataFrame) -> list[dict]:
    """Convert the filtered DataFrame into a list of dicts matching the Player model."""
    rows = []
    for _, r in df.iterrows():
        full_name_parts = []
        if pd.notna(r.get("name_first")):
            full_name_parts.append(str(r["name_first"]).strip())
        if pd.notna(r.get("name_last")):
            full_name_parts.append(str(r["name_last"]).strip())
        full_name = " ".join(full_name_parts) or "Unknown"

        mlb_id = int(r["key_mlbam"])

        fangraphs_id = None
        if pd.notna(r.get("key_fangraphs")):
            try:
                fangraphs_id = int(r["key_fangraphs"])
            except (ValueError, TypeError):
                pass

        bref_id = None
        if pd.notna(r.get("key_bbref")):
            bref_id = str(r["key_bbref"]).strip() or None

        bats = None
        if pd.notna(r.get("bats")):
            bats = str(r["bats"]).strip() or None

        throws = None
        if pd.notna(r.get("throws")):
            throws = str(r["throws"]).strip() or None

        rows.append(
            {
                "full_name": full_name,
                "mlb_id": mlb_id,
                "fangraphs_id": fangraphs_id,
                "bref_id": bref_id,
                "bats": bats,
                "throws": throws,
            }
        )
    return rows


async def upsert_players(rows: list[dict]) -> int:
    """Insert or update players using SQLite upsert (ON CONFLICT)."""
    if not rows:
        print("No rows to insert.")
        return 0

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    upserted = 0
    batch_size = 500

    async with async_session() as session:
        async with session.begin():
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                stmt = sqlite_insert(Player.__table__).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["mlb_id"],
                    set_={
                        "full_name": stmt.excluded.full_name,
                        "fangraphs_id": stmt.excluded.fangraphs_id,
                        "bref_id": stmt.excluded.bref_id,
                        "bats": stmt.excluded.bats,
                        "throws": stmt.excluded.throws,
                    },
                )
                await session.execute(stmt)
                upserted += len(batch)

    print(f"Inserted/updated {upserted:,} players")
    return upserted


async def main() -> None:
    print("=== Player ID Crosswalk Ingestion ===")
    csv_text = await download_people_csv()
    df = parse_and_filter(csv_text)
    rows = build_player_rows(df)
    await upsert_players(rows)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
