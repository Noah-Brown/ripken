# Ripken

A personal, real-time fantasy baseball dashboard that merges MLB operational data (lineups, bullpen usage, prospect call-ups, advanced stats) with Yahoo Fantasy league context.

## Quick Start

```bash
# Install dependencies
make install

# Copy and fill in environment variables
cp .env.example .env

# Start both backend and frontend
make dev
```

- Backend (FastAPI): http://localhost:8000
- Frontend (Next.js): http://localhost:3000

## Project Structure

```
ripken/
├── backend/          # Python / FastAPI
├── frontend/         # Next.js 14 (App Router)
├── shared/           # Shared constants
├── data/             # Static data files
├── docs/             # Project documentation
└── Makefile
```

See [docs/BLUEPRINT.md](docs/BLUEPRINT.md) for the full project blueprint.
