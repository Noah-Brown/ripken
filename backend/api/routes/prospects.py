"""Prospect watchlist API routes."""

import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.analytics.prospect_signals import compute_prospect_signals
from backend.database.models import Player, Prospect
from backend.ingestion.mlb_stats_api import fetch_milb_stats, resolve_mlb_id

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


@router.get("/prospects/{prospect_id}/stats")
async def get_prospect_stats(
    prospect_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """Fetch MiLB stats for a prospect, using cached data if fresh."""
    result = await db.execute(
        select(Prospect, Player)
        .join(Player, Prospect.player_id == Player.id)
        .where(Prospect.id == prospect_id)
    )
    row = result.one_or_none()
    if not row:
        return {"error": "Prospect not found"}

    prospect, player = row

    # Check cache — return cached stats if less than 6 hours old
    if prospect.stats_fetched_at and prospect.minor_league_stats:
        cache_age = datetime.now(timezone.utc) - prospect.stats_fetched_at.replace(
            tzinfo=timezone.utc
        )
        if cache_age < timedelta(hours=6):
            try:
                cached = json.loads(prospect.minor_league_stats)
                return {
                    "player_id": player.id,
                    "mlb_id": player.mlb_id,
                    "season": datetime.now().year,
                    "stats": cached if isinstance(cached, list) else [],
                    "cached": True,
                }
            except (json.JSONDecodeError, TypeError):
                pass

    # Resolve MLB ID if we don't have one
    mlb_id = player.mlb_id
    if not mlb_id and player.fangraphs_id:
        # Try Chadwick crosswalk: look up by fangraphs_id (integer)
        xwalk = await db.execute(
            select(Player.mlb_id).where(
                Player.fangraphs_id == player.fangraphs_id,
                Player.mlb_id.isnot(None),
            )
        )
        row = xwalk.first()
        if row and row[0]:
            mlb_id = row[0]
            player.mlb_id = mlb_id
            await db.commit()
    if not mlb_id:
        mlb_id = await resolve_mlb_id(player.full_name)
        if mlb_id:
            player.mlb_id = mlb_id
            await db.commit()

    if not mlb_id:
        return {
            "player_id": player.id,
            "mlb_id": None,
            "season": datetime.now().year,
            "stats": [],
            "error": "Could not resolve MLB ID for this player",
        }

    # Fetch fresh stats
    stats = await fetch_milb_stats(mlb_id)

    # Cache the results
    prospect.minor_league_stats = json.dumps(stats)
    prospect.stats_fetched_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "player_id": player.id,
        "mlb_id": mlb_id,
        "season": datetime.now().year,
        "stats": stats,
        "cached": False,
    }


@router.post("/prospects/import")
async def import_prospects_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
):
    """Import prospect rankings from a FanGraphs 'The Board' CSV.

    Expected columns: Name, Org, Pos, FV, Current Level, ETA, Dynasty Rank,
    Re-Draft Rank, Trend, Age, Ht, Wt, B, T, Report, Video, PlayerId
    """
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    updated = 0
    skipped = 0

    for row in reader:
        # Flexible column mapping — supports both FanGraphs "The Board" and simpler formats
        name = row.get("Name") or row.get("Player") or row.get("name") or ""
        org = row.get("Org") or row.get("Team") or row.get("org") or row.get("Organization") or ""
        level = (
            row.get("Current Level")
            or row.get("Level")
            or row.get("level")
            or ""
        )
        rank_str = (
            row.get("Dynasty Rank")
            or row.get("Rank")
            or row.get("rank")
            or row.get("#")
            or ""
        )
        redraft_rank_str = row.get("Re-Draft Rank") or ""
        eta = row.get("ETA") or row.get("eta") or ""
        position = row.get("Pos") or row.get("Position") or row.get("position") or ""
        fv_str = row.get("FV") or ""
        report = row.get("Report") or ""
        video = row.get("Video") or ""
        trend = row.get("Trend") or ""
        age = row.get("Age") or ""
        height = row.get("Ht") or ""
        weight = row.get("Wt") or ""
        bats = row.get("B") or row.get("Bats") or ""
        throws = row.get("T") or row.get("Throws") or ""
        player_id_str = row.get("PlayerId") or row.get("playerid") or ""

        if not name:
            skipped += 1
            continue

        # Parse numeric fields (FanGraphs uses "45+", "40+" etc. for FV — strip the "+")
        try:
            rank = int(rank_str) if rank_str else None
        except ValueError:
            rank = None
        try:
            redraft_rank = int(redraft_rank_str) if redraft_rank_str else None
        except ValueError:
            redraft_rank = None
        try:
            fv = int(fv_str.rstrip("+")) if fv_str else None
        except ValueError:
            fv = None

        # Find or create player — use first() to handle duplicate names gracefully
        result = await db.execute(
            select(Player).where(Player.full_name == name.strip())
        )
        player = result.scalars().first()

        if not player:
            player = Player(
                full_name=name.strip(),
                team=org.strip() if org else None,
                position=position.strip() if position else None,
                bats=bats.strip() if bats else None,
                throws=throws.strip() if throws else None,
                fangraphs_id_str=player_id_str.strip() if player_id_str else None,
                status="minors",
                is_prospect=1,
            )
            db.add(player)
            await db.flush()
        else:
            # Update player fields from CSV
            if position:
                player.position = position.strip()
            if bats:
                player.bats = bats.strip()
            if throws:
                player.throws = throws.strip()
            if player_id_str:
                player.fangraphs_id_str = player_id_str.strip()
            player.is_prospect = 1

        # Check if prospect already exists — update instead of skipping
        existing_result = await db.execute(
            select(Prospect).where(Prospect.player_id == player.id)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.org = org.strip() or existing.org
            existing.level = level.strip() or existing.level
            existing.fangraphs_rank = rank if rank is not None else existing.fangraphs_rank
            existing.redraft_rank = redraft_rank if redraft_rank is not None else existing.redraft_rank
            existing.eta = eta.strip() if eta else existing.eta
            existing.fv = fv if fv is not None else existing.fv
            existing.scouting_report = report.strip() if report else existing.scouting_report
            existing.video_url = video.strip() if video else existing.video_url
            existing.trend = trend.strip() if trend else existing.trend
            existing.age = age.strip() if age else existing.age
            existing.height = height.strip() if height else existing.height
            existing.weight = weight.strip() if weight else existing.weight
            updated += 1
        else:
            prospect = Prospect(
                player_id=player.id,
                org=org.strip() or "Unknown",
                level=level.strip(),
                fangraphs_rank=rank,
                redraft_rank=redraft_rank,
                eta=eta.strip() if eta else None,
                fv=fv,
                scouting_report=report.strip() if report else None,
                video_url=video.strip() if video else None,
                trend=trend.strip() if trend else None,
                age=age.strip() if age else None,
                height=height.strip() if height else None,
                weight=weight.strip() if weight else None,
                on_40_man=0,
            )
            db.add(prospect)
            imported += 1

    await db.commit()
    logger.info(f"Imported {imported}, updated {updated}, skipped {skipped}")
    return {"imported": imported, "updated": updated, "skipped": skipped}
