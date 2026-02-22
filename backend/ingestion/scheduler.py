"""APScheduler job definitions for data ingestion."""

import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.config import settings
from backend.database.connection import async_session

logger = logging.getLogger(__name__)


async def _run_job(name: str, coro_factory):
    """Wrapper that logs and handles exceptions for each job."""
    logger.info(f"Job [{name}] starting...")
    try:
        async with async_session() as db:
            await coro_factory(db)
        logger.info(f"Job [{name}] completed.")
    except Exception:
        logger.exception(f"Job [{name}] failed.")


# ---------------------------------------------------------------------------
# Individual job functions (imported lazily to avoid circular imports)
# ---------------------------------------------------------------------------


async def job_sync_schedule():
    from backend.ingestion.mlb_stats import fetch_schedule

    today = date.today()
    end = today + timedelta(days=7)

    async def run(db):
        await fetch_schedule(db, today.isoformat(), end.isoformat())

    await _run_job("sync_schedule", run)


async def job_sync_rosters():
    from backend.ingestion.mlb_stats import fetch_rosters

    await _run_job("sync_rosters", fetch_rosters)


async def job_sync_probable_pitchers():
    from backend.ingestion.mlb_stats import fetch_probable_pitchers

    today = date.today()
    end = today + timedelta(days=5)

    async def run(db):
        await fetch_probable_pitchers(db, today.isoformat(), end.isoformat())

    await _run_job("sync_probable_pitchers", run)


async def job_sync_transactions():
    from backend.ingestion.mlb_stats import fetch_transactions

    today = date.today()
    start = today - timedelta(days=1)

    async def run(db):
        await fetch_transactions(db, start.isoformat(), today.isoformat())

    await _run_job("sync_transactions", run)


async def job_sync_savant():
    from backend.ingestion.savant import sync_savant_stats

    await _run_job("sync_savant", sync_savant_stats)


async def job_sync_fangraphs():
    from backend.ingestion.fangraphs import sync_fangraphs_stats

    await _run_job("sync_fangraphs", sync_fangraphs_stats)


async def job_sync_fangraphs_projections():
    from backend.ingestion.fangraphs import sync_fangraphs_projections

    await _run_job("sync_fangraphs_projections", sync_fangraphs_projections)


async def job_sync_yahoo_rosters():
    from backend.yahoo.sync import sync_all_rosters

    await _run_job("sync_yahoo_rosters", sync_all_rosters)


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler with all ingestion jobs."""
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    # MLB schedule — every 6 hours
    scheduler.add_job(job_sync_schedule, "interval", hours=6, id="sync_schedule")

    # MLB rosters — every 30 minutes
    scheduler.add_job(job_sync_rosters, "interval", minutes=30, id="sync_rosters")

    # Probable pitchers — every 2 hours
    scheduler.add_job(
        job_sync_probable_pitchers, "interval", hours=2, id="sync_probable_pitchers"
    )

    # Transactions — every 30 minutes
    scheduler.add_job(job_sync_transactions, "interval", minutes=30, id="sync_transactions")

    # Savant stats — nightly at 3 AM ET
    scheduler.add_job(
        job_sync_savant, "cron", hour=settings.stats_sync_hour, minute=0, id="sync_savant"
    )

    # FanGraphs stats — nightly at 3:30 AM ET
    scheduler.add_job(
        job_sync_fangraphs, "cron", hour=settings.stats_sync_hour, minute=30, id="sync_fangraphs"
    )

    # FanGraphs projections — weekly on Sunday at midnight
    scheduler.add_job(
        job_sync_fangraphs_projections,
        "cron",
        day_of_week="sun",
        hour=0,
        minute=0,
        id="sync_fangraphs_projections",
    )

    # Yahoo rosters — every 15 minutes
    scheduler.add_job(
        job_sync_yahoo_rosters, "interval", minutes=15, id="sync_yahoo_rosters"
    )

    return scheduler


async def run_startup_jobs():
    """Run critical jobs on startup so the dashboard isn't empty."""
    logger.info("Running startup data sync...")
    await job_sync_schedule()
    await job_sync_probable_pitchers()
    await job_sync_rosters()
    logger.info("Startup sync complete.")
