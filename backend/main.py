import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.auth import router as auth_router
from backend.api.routes.bullpen import router as bullpen_router
from backend.api.routes.dashboard import router as dashboard_router
from backend.api.routes.lineups import router as lineups_router
from backend.api.routes.pitching import router as pitching_router
from backend.api.routes.roster import router as roster_router
from backend.api.routes.waivers import router as waivers_router
from backend.database.connection import engine
from backend.database.models import Base
from backend.ingestion.scheduler import create_scheduler, run_startup_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Start scheduler
    scheduler = create_scheduler()
    scheduler.start()

    # Run critical data loads in background so server starts immediately
    asyncio.create_task(run_startup_jobs())

    yield

    # Shutdown
    scheduler.shutdown(wait=False)


app = FastAPI(title="Ripken", description="Fantasy Baseball Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(bullpen_router)
app.include_router(dashboard_router)
app.include_router(lineups_router)
app.include_router(pitching_router)
app.include_router(roster_router)
app.include_router(waivers_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
