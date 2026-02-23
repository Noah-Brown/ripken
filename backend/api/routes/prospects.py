"""Prospect watchlist API routes."""

import csv
import io
import json
import logging

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.analytics.prospect_signals import compute_prospect_signals
from backend.database.models import Player, Prospect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["prospects"])


@router.get("/prospects")
async def get_prospects(db: AsyncSession = Depends(get_db_session)):
    """List all watched prospects with call-up signals."""
    scored = await compute_prospect_signals(db)
    return {"prospects": scored}


@router.post("/prospects")
async def add_prospect(
    player_id: int,
    org: str,
    level: str = "",
    user_rank: int | None = None,
    eta: str | None = None,
    scouting_notes: str | None = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Add a player to the prospect watchlist."""
    # Check player exists
    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        return {"error": "Player not found"}

    # Check not already watched
    result = await db.execute(
        select(Prospect).where(Prospect.player_id == player_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {"error": "Player already on watchlist"}

    prospect = Prospect(
        player_id=player_id,
        org=org,
        level=level,
        user_rank=user_rank,
        eta=eta,
        scouting_notes=scouting_notes,
        on_40_man=0,
    )
    db.add(prospect)
    await db.commit()

    # Mark player as prospect
    player.is_prospect = 1
    await db.commit()

    return {"id": prospect.id, "player_id": player_id}


@router.put("/prospects/{prospect_id}")
async def update_prospect(
    prospect_id: int,
    user_rank: int | None = None,
    level: str | None = None,
    eta: str | None = None,
    scouting_notes: str | None = None,
    on_40_man: int | None = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Update a prospect on the watchlist."""
    result = await db.execute(select(Prospect).where(Prospect.id == prospect_id))
    prospect = result.scalar_one_or_none()
    if not prospect:
        return {"error": "Prospect not found"}

    if user_rank is not None:
        prospect.user_rank = user_rank
    if level is not None:
        prospect.level = level
    if eta is not None:
        prospect.eta = eta
    if scouting_notes is not None:
        prospect.scouting_notes = scouting_notes
    if on_40_man is not None:
        prospect.on_40_man = on_40_man

    await db.commit()
    return {"id": prospect.id, "updated": True}


@router.delete("/prospects/{prospect_id}")
async def remove_prospect(
    prospect_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """Remove a prospect from the watchlist."""
    result = await db.execute(select(Prospect).where(Prospect.id == prospect_id))
    prospect = result.scalar_one_or_none()
    if not prospect:
        return {"error": "Prospect not found"}

    # Unmark player as prospect
    player_result = await db.execute(
        select(Player).where(Player.id == prospect.player_id)
    )
    player = player_result.scalar_one_or_none()
    if player:
        player.is_prospect = 0

    await db.execute(delete(Prospect).where(Prospect.id == prospect_id))
    await db.commit()
    return {"deleted": True}


@router.post("/prospects/import")
async def import_prospects_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
):
    """Import prospect rankings from a FanGraphs-style CSV.

    Expected columns (flexible): Name/Player, Team/Org, Level, Rank, ETA
    """
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    skipped = 0

    for row in reader:
        # Flexible column mapping
        name = row.get("Name") or row.get("Player") or row.get("name") or ""
        org = row.get("Team") or row.get("Org") or row.get("org") or row.get("Organization") or ""
        level = row.get("Level") or row.get("level") or ""
        rank_str = row.get("Rank") or row.get("rank") or row.get("#") or ""
        eta = row.get("ETA") or row.get("eta") or ""

        if not name:
            skipped += 1
            continue

        # Try to find the player in our DB
        result = await db.execute(
            select(Player).where(Player.full_name == name.strip())
        )
        player = result.scalar_one_or_none()

        if not player:
            # Create a minimal player record
            player = Player(
                full_name=name.strip(),
                team=org.strip() if org else None,
                position=row.get("Position") or row.get("Pos") or None,
                status="minors",
                is_prospect=1,
            )
            db.add(player)
            await db.flush()

        # Check if already on watchlist
        existing = await db.execute(
            select(Prospect).where(Prospect.player_id == player.id)
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        try:
            rank = int(rank_str) if rank_str else None
        except ValueError:
            rank = None

        prospect = Prospect(
            player_id=player.id,
            org=org.strip() or "Unknown",
            level=level.strip(),
            user_rank=rank,
            eta=eta.strip() if eta else None,
            on_40_man=0,
        )
        db.add(prospect)
        player.is_prospect = 1
        imported += 1

    await db.commit()
    logger.info(f"Imported {imported} prospects, skipped {skipped}")
    return {"imported": imported, "skipped": skipped}
