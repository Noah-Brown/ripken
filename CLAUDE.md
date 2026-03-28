# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ripken is a real-time fantasy baseball dashboard that merges MLB operational data (lineups, bullpen usage, prospects, advanced stats) with Yahoo Fantasy league context. It fetches, caches briefly, and layers analytics on top of external data sources to answer "how does this affect **my** teams?"

## Commands

```bash
make install          # Install backend (uv) and frontend (npm) dependencies
make dev              # Run backend (port 8000) and frontend (port 3000) in parallel
make backend          # Run only FastAPI backend
make frontend         # Run only Next.js frontend
make db-init          # Create/reset SQLite database tables
make test             # pytest backend/tests -v
make lint             # ruff check backend/ shared/
```

Setup requires `cp .env.example .env` and filling in Yahoo OAuth2 credentials.

## Deployment

Deployed on a Digital Ocean droplet (Ubuntu 24.04) via Docker Compose with three services:
- **Caddy** — reverse proxy with automatic HTTPS (Let's Encrypt)
- **backend** — FastAPI container
- **frontend** — Next.js container (server-side rendering)

Production URL: `https://ripken.noahbrown.io`

```bash
ssh ripken "cd ~/ripken && git pull && docker compose up -d --build"   # Deploy from local
ssh ripken "docker compose -f ~/ripken/docker-compose.yml logs -f"    # Tail logs
```

Key production env vars: `SITE_ADDRESS`, `DASHBOARD_PASSWORD`, `SESSION_SECRET`, `FRONTEND_URL`, `ALLOWED_ORIGINS`, `NEXT_PUBLIC_API_URL`, `YAHOO_REDIRECT_URI`. See `.env.example` and `docs/DEPLOY.md`.

## Architecture

**Monorepo** with a Python FastAPI backend and Next.js 14 frontend communicating over REST.

### Backend (`/backend`)

- **`main.py`** — FastAPI app with lifespan that creates DB tables, starts APScheduler, and runs startup ingestion jobs. CORS allows `localhost:3000`.
- **`config.py`** — Pydantic Settings loading from `.env`. All config (DB URL, Yahoo OAuth, scheduling params, external API URLs, feature flags) lives here.
- **`database/`** — Async SQLAlchemy with aiosqlite. `connection.py` exports `get_db()` dependency. `models.py` defines 14 tables using `DeclarativeBase`. Core tables: `players`, `player_stats`, `games`, `lineups`, `probable_pitchers`, `pitcher_appearances`, `reliever_roles`, `transactions`, `prospects`. User-scoped: `user_accounts`, `user_leagues`, `user_rosters`, `user_watchlist`, `alerts`.
- **`api/routes/`** — 10 routers: alerts, auth, bullpen, dashboard, lineups, matchup, pitching, prospects, roster, waivers.
- **`ingestion/`** — Data pipeline pulling from MLB Stats API (free, no auth), Baseball Savant (CSV), FanGraphs (CSV), and Chadwick Bureau (player ID crosswalk). Runs on APScheduler cron jobs (lineups every 10min during games, rosters every 30min, stats nightly).
- **`analytics/`** — Scoring engines: start/sit confidence (platoon 30%, pitcher weakness 25%, park factor 20%, recent form 15%, baseline 10%), reliever role inference, H2H matchup projections, prospect call-up likelihood (Hot/Warm/Cold), waiver wire ranking.
- **`yahoo/`** — OAuth2 flow and Yahoo Fantasy API wrapper for leagues, rosters, free agents, matchups.

### Frontend (`/frontend`)

Next.js 14 App Router with React 19 and Tailwind CSS v4. Pages mirror backend modules: dashboard home, roster, lineups, pitching, bullpen, prospects, matchup, waivers. API client and shared types in `src/lib/`.

### Shared (`/shared`)

Shared constants used by both backend and frontend.

## Code Style

- **Python**: Ruff linter, line-length 100, target Python 3.11
- **Frontend**: ESLint, TypeScript strict mode, Tailwind CSS
- **Testing**: pytest with pytest-asyncio for async route/service tests

## Data Flow

External APIs → `ingestion/` → SQLite (`data/fantasy_dashboard.db`) → `analytics/` scoring → `api/routes/` → Next.js frontend

Yahoo Fantasy data flows through OAuth2 (`/auth/yahoo/callback`) → `yahoo/` client → user-scoped DB tables.

## Development Status

Phases 1-4 complete (foundation, Yahoo integration, core modules, smart features). App is deployed to production on a VPS. Phase 5 (polish: mobile responsiveness, error handling, multi-user/Postgres migration) is partially started (deployment done). See `docs/BLUEPRINT.md` for full spec and algorithm details.
