# VPS Deployment Design — ripken.noahbrown.io

## Overview

Migrate the Ripken fantasy baseball dashboard from local development to a Digital Ocean VPS, accessible at `https://ripken.noahbrown.io`. Single-user personal app with password-gated access.

**Key decisions:**
- Docker Compose for orchestration (3 containers: Caddy, backend, frontend)
- Caddy for reverse proxy + automatic HTTPS
- SQLite stays (single-user, low data volume)
- Simple password auth in Next.js (no NextAuth, no user accounts)
- Manual deploy via `git pull` + `docker compose up --build`

---

## Architecture

```
ripken.noahbrown.io
        |
        v
+---------------+
|    Caddy       |  :80 -> redirect to :443
|  (container)   |  :443 (auto TLS via Let's Encrypt)
|                |
|  /api/*   ----------> backend:8000 (FastAPI/Uvicorn)
|  /auth/*  ----------> backend:8000
|  /health  ----------> backend:8000
|  /*       ----------> frontend:3000 (Next.js)
+---------------+
        |
   +----+------+
   v           v
+--------+ +----------+
|Backend | | Frontend |
|(Python)| |(Next.js) |
+---+----+ +----------+
    |
    v
+----------+
| SQLite   |  mounted volume: ./data/
| (file)   |
+----------+
```

Three Docker containers on an internal network. Only Caddy exposes ports (80, 443) to the host. Backend and frontend are only reachable through Caddy.

---

## Auth Flow

Password gate implemented entirely in Next.js:

1. **Login page** (`/login`) — single password field form.
2. **API route** (`/api/auth/login`) — checks password against `DASHBOARD_PASSWORD` env var. On success, sets a signed cookie:
   - `httpOnly: true` — not accessible to JavaScript
   - `secure: true` — only sent over HTTPS
   - `sameSite: strict` — not sent on cross-site requests
   - Signed using `SESSION_SECRET` env var (random string, generated once)
   - 30-day expiry
3. **Middleware** (`middleware.ts`) — runs on every request. Validates the signed cookie. Redirects to `/login` if missing/invalid. Excludes `/login`, `/api/auth/*`, and `/_next/*` from the check.
4. **Logout** (`/api/auth/logout`) — clears the cookie.

Backend API routes (`/api/*`, `/auth/*`, `/health`) are **not** behind the password gate. They're low-risk (fantasy roster data) and need to be accessible for Yahoo OAuth callbacks and health checks.

Cookie signing uses the Web Crypto API built into the Next.js runtime (zero additional dependencies).

---

## Docker Setup

### Backend Dockerfile

- Base: `python:3.13-slim`
- Install `uv` for package management
- Copy `pyproject.toml` + `uv.lock`, install dependencies
- Copy `backend/` and `shared/` source code
- Volume mount: `./data:/app/data` for SQLite persistence
- Command: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`

### Frontend Dockerfile

- Multi-stage build on `node:22-alpine`
- Stage 1 (build): `npm ci` + `next build`
- Stage 2 (run): copy standalone build output, run `next start --port 3000`
- Build-time env: `NEXT_PUBLIC_API_URL`
- Runtime env: `DASHBOARD_PASSWORD`, `SESSION_SECRET`

### Caddyfile

```
ripken.noahbrown.io {
    handle /api/* {
        reverse_proxy backend:8000
    }
    handle /auth/* {
        reverse_proxy backend:8000
    }
    handle /health {
        reverse_proxy backend:8000
    }
    handle {
        reverse_proxy frontend:3000
    }
}
```

Caddy automatically provisions and renews Let's Encrypt certificates for the domain.

### docker-compose.yml

Services:
- **caddy** — official Caddy image, ports 80:80 and 443:443, mounts Caddyfile and a volume for cert data
- **backend** — built from `Dockerfile.backend`, mounts `./data`, loads `.env`
- **frontend** — built from `Dockerfile.frontend`, loads `.env`

All three on a shared Docker network (`ripken-net`). No ports exposed to host except Caddy's 80/443.

`.env` file provides all configuration (not committed to git).

---

## Code Changes

### Backend

1. **`backend/config.py`** — Add `allowed_origins: str` and `frontend_url: str` fields to Pydantic settings.
2. **`backend/main.py`** — Replace hardcoded CORS origins with `settings.allowed_origins` (comma-separated string parsed to list). Keep localhost defaults for dev.
3. **`backend/api/routes/auth.py`** — Already uses `FRONTEND_URL` env var (uncommitted change). No further changes needed.

### Frontend

4. **`frontend/src/app/login/page.tsx`** — New. Simple password form page.
5. **`frontend/src/app/api/auth/login/route.ts`** — New. Validates password, sets signed cookie.
6. **`frontend/src/app/api/auth/logout/route.ts`** — New. Clears auth cookie.
7. **`frontend/src/middleware.ts`** — New. Checks for valid signed cookie on all routes, redirects to `/login` if invalid. Excludes public paths.
8. **`frontend/src/lib/auth.ts`** — New. Cookie signing/verification utilities using Web Crypto API.

### Configuration

9. **`.env.example`** — Add `DASHBOARD_PASSWORD`, `SESSION_SECRET`, `FRONTEND_URL`, `ALLOWED_ORIGINS`.

### New deployment files

10. **`Dockerfile.backend`** — Backend container definition.
11. **`Dockerfile.frontend`** — Frontend container definition.
12. **`docker-compose.yml`** — Orchestration for all three services.
13. **`Caddyfile`** — Reverse proxy configuration.
14. **`.dockerignore`** — Exclude `.venv`, `node_modules`, `.git`, `data/*.db`.

---

## Environment Variables (Production)

```
# Auth
DASHBOARD_PASSWORD=<your-chosen-password>
SESSION_SECRET=<random-64-char-string>

# URLs
FRONTEND_URL=https://ripken.noahbrown.io
ALLOWED_ORIGINS=https://ripken.noahbrown.io
NEXT_PUBLIC_API_URL=https://ripken.noahbrown.io

# Yahoo OAuth2
YAHOO_CLIENT_ID=<existing>
YAHOO_CLIENT_SECRET=<existing>
YAHOO_REDIRECT_URI=https://ripken.noahbrown.io/auth/yahoo/callback

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/fantasy_dashboard.db

# Scheduling
LINEUP_CHECK_START_HOUR=14
LINEUP_CHECK_END_HOUR=23
LINEUP_CHECK_INTERVAL_MINUTES=10
STATS_SYNC_HOUR=3
TIMEZONE=America/New_York

# External Data
MLB_STATS_API_BASE=https://statsapi.mlb.com/api/v1
SAVANT_BASE_URL=https://baseballsavant.mlb.com
FANGRAPHS_BASE_URL=https://www.fangraphs.com

# Feature Flags
ENABLE_ALERTS=true
ENABLE_PROSPECT_TRACKING=true
```

---

## VPS Setup (One-Time)

1. Provision Digital Ocean droplet: Ubuntu 24.04, 1GB RAM / 1 vCPU ($6/mo)
2. Install Docker + Docker Compose
3. Configure UFW firewall: allow 22 (SSH), 80, 443; deny all else
4. Clone repo, create `.env` with production values
5. Add DNS A record: `ripken.noahbrown.io` -> droplet IP
6. `docker compose up -d`
7. Update Yahoo Developer App redirect URI to `https://ripken.noahbrown.io/auth/yahoo/callback`
8. Authenticate at `https://ripken.noahbrown.io/auth/yahoo`

---

## Deployment Workflow

```bash
# On the droplet:
cd ~/ripken
git pull
docker compose up -d --build
```

No CI/CD. Manual deploy is fine for a personal app.

---

## Backups

Daily cron job on the droplet:

```bash
# /etc/cron.d/ripken-backup
0 4 * * * root sqlite3 /root/ripken/data/fantasy_dashboard.db ".backup /root/ripken/backups/fantasy_dashboard_$(date +\%Y\%m\%d).db" && find /root/ripken/backups -name "*.db" -mtime +7 -delete
```

Uses SQLite's `.backup` command (safe even while the app is running). Keeps 7 days of backups.

---

## Monitoring

- **UptimeRobot** (free tier) pinging `https://ripken.noahbrown.io/health`
- Docker logs: `docker compose logs -f` for troubleshooting
- Caddy access logs for request visibility
