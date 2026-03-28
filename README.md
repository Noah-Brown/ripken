# Ripken

A personal, real-time fantasy baseball dashboard that merges MLB operational data (lineups, bullpen usage, prospect call-ups, advanced stats) with Yahoo Fantasy league context.

## Quick Start (Local Development)

```bash
# Install dependencies (requires uv and npm)
make install

# Copy and fill in environment variables
cp .env.example .env

# Start both backend and frontend
make dev
```

- Backend (FastAPI): http://localhost:8000
- Frontend (Next.js): http://localhost:3000

## Deployment

Deployed via Docker Compose on a Digital Ocean droplet with Caddy as a reverse proxy (automatic HTTPS via Let's Encrypt).

```bash
# Production deploy
cp .env.example .env   # fill in production values
docker compose up -d --build
```

See [docs/DEPLOY.md](docs/DEPLOY.md) for the full VPS deployment guide.

## Project Structure

```
ripken/
├── backend/              # Python / FastAPI
├── frontend/             # Next.js 14 (App Router)
├── shared/               # Shared constants
├── data/                 # SQLite database and static data
├── docs/                 # Project documentation
├── docker-compose.yml    # Production deployment (Caddy + backend + frontend)
├── Dockerfile.backend
├── Dockerfile.frontend
├── Caddyfile
└── Makefile
```

See [docs/BLUEPRINT.md](docs/BLUEPRINT.md) for the full project blueprint.
