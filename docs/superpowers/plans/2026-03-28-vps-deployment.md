# VPS Deployment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the Ripken fantasy baseball dashboard to a Digital Ocean VPS at `https://ripken.noahbrown.io` with Docker Compose, Caddy reverse proxy, and password-gated access.

**Architecture:** Three Docker containers (Caddy, FastAPI backend, Next.js frontend) on an internal network. Caddy handles TLS and routing. Next.js middleware provides password auth via signed cookies. SQLite persists via bind-mounted volume.

**Tech Stack:** Docker Compose, Caddy 2, Python 3.13 + FastAPI + Uvicorn, Next.js 16 (standalone output), SQLite with WAL mode.

**Spec:** `docs/superpowers/specs/2026-03-28-vps-deployment-design.md`

---

## File Map

### New Files
| File | Responsibility |
|------|---------------|
| `Caddyfile` | Reverse proxy routing + auto TLS |
| `Dockerfile.backend` | Backend container build |
| `Dockerfile.frontend` | Frontend multi-stage container build |
| `docker-compose.yml` | Service orchestration |
| `.dockerignore` | Exclude dev artifacts from build context |
| `frontend/src/lib/auth.ts` | Cookie signing/verification (Web Crypto API) |
| `frontend/src/app/login/page.tsx` | Password login form |
| `frontend/src/app/api/auth/login/route.ts` | Login API (validate password, set cookie) |
| `frontend/src/app/api/auth/logout/route.ts` | Logout API (clear cookie) |
| `frontend/src/middleware.ts` | Auth gate (check cookie on every request) |

### Modified Files
| File | Change |
|------|--------|
| `backend/config.py` | Add `allowed_origins`, `frontend_url` fields |
| `backend/main.py` | Use `settings.allowed_origins` for CORS |
| `backend/api/routes/auth.py` | Use `settings.frontend_url` instead of `os.environ` |
| `backend/database/connection.py` | Enable WAL mode on SQLite |
| `frontend/next.config.ts` | Add `output: 'standalone'` |
| `frontend/src/lib/api.ts` | Split server-side vs client-side API base URL |
| `frontend/src/app/page.tsx` | Fix hardcoded `localhost:8000` Yahoo auth link |
| `.env.example` | Add new env vars |

---

## Task 1: Backend Config + CORS

Update backend configuration to support production URLs.

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/main.py`
- Modify: `backend/api/routes/auth.py`

- [ ] **Step 1: Add `allowed_origins` and `frontend_url` to settings**

In `backend/config.py`, add two fields to the `Settings` class:

```python
# URLs
allowed_origins: str = "http://localhost:3000"
frontend_url: str = "http://localhost:3000"
```

Add these after the `yahoo_redirect_uri` field (line 11).

- [ ] **Step 2: Update CORS to use settings**

In `backend/main.py`, import settings and replace the hardcoded CORS origins:

```python
from backend.config import settings
```

Replace the `allow_origins` line in `add_middleware`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 3: Update auth.py to use settings.frontend_url**

In `backend/api/routes/auth.py`:
- Remove `import os`
- Add `from backend.config import settings`
- Replace `os.environ.get("FRONTEND_URL", "http://localhost:3000")` with `settings.frontend_url`

The redirect line becomes:
```python
return RedirectResponse(f"{settings.frontend_url}/?yahoo_connected=1")
```

- [ ] **Step 4: Verify backend starts**

Run: `. .venv/bin/activate && timeout 10 uvicorn backend.main:app --host 0.0.0.0 --port 8001 2>&1 || true`

Expected: App starts without import errors. "Application startup complete." in output.

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/main.py backend/api/routes/auth.py
git commit -m "feat: make CORS origins and frontend URL configurable via env vars"
```

---

## Task 2: SQLite WAL Mode

Enable WAL journal mode for safe online backups.

**Files:**
- Modify: `backend/database/connection.py`

- [ ] **Step 1: Add WAL mode event listener**

In `backend/database/connection.py`, add imports and a SQLAlchemy event listener that sets WAL mode on each new raw connection. Add the import at the top and the event listener immediately after the existing `engine = create_async_engine(...)` line (do NOT duplicate the engine line):

Add import:
```python
from sqlalchemy import event
```

Add after the existing `engine = ...` line:
```python
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_wal(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
```

- [ ] **Step 2: Verify WAL mode is active**

Run:
```bash
. .venv/bin/activate && python3 -c "
import asyncio
from backend.database.connection import engine
async def check():
    async with engine.begin() as conn:
        result = await conn.exec_driver_sql('PRAGMA journal_mode')
        row = result.fetchone()
        print(f'journal_mode: {row[0]}')
        assert row[0] == 'wal', f'Expected wal, got {row[0]}'
        print('OK')
asyncio.run(check())
"
```

Expected: `journal_mode: wal` and `OK`.

- [ ] **Step 3: Commit**

```bash
git add backend/database/connection.py
git commit -m "feat: enable SQLite WAL mode for safe online backups"
```

---

## Task 3: Frontend Auth — Cookie Utilities

Create the cookie signing/verification library.

**Files:**
- Create: `frontend/src/lib/auth.ts`

- [ ] **Step 1: Create auth.ts with sign/verify functions**

Create `frontend/src/lib/auth.ts`:

```typescript
import { cookies } from "next/headers";

const COOKIE_NAME = "ripken_session";
const MAX_AGE = 60 * 60 * 24 * 30; // 30 days

function getSecret(): Uint8Array {
  const secret = process.env.SESSION_SECRET;
  if (!secret) throw new Error("SESSION_SECRET env var is required");
  return new TextEncoder().encode(secret);
}

async function getKey(): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    getSecret(),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

function hexEncode(buf: ArrayBuffer): string {
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function hexDecode(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16);
  }
  return bytes;
}

export async function createSessionCookie(): Promise<void> {
  const payload = JSON.stringify({ auth: true, iat: Date.now() });
  const key = await getKey();
  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(payload),
  );
  const token = `${Buffer.from(payload).toString("base64url")}.${hexEncode(sig)}`;

  const cookieStore = await cookies();
  cookieStore.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    maxAge: MAX_AGE,
    path: "/",
  });
}

export async function verifySessionCookie(cookieValue: string): Promise<boolean> {
  try {
    const [payloadB64, sigHex] = cookieValue.split(".");
    if (!payloadB64 || !sigHex) return false;

    const payload = Buffer.from(payloadB64, "base64url");
    const key = await getKey();
    const valid = await crypto.subtle.verify(
      "HMAC",
      key,
      hexDecode(sigHex),
      payload,
    );
    return valid;
  } catch {
    return false;
  }
}

export async function clearSessionCookie(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(COOKIE_NAME);
}

export const SESSION_COOKIE_NAME = COOKIE_NAME;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/auth.ts
git commit -m "feat: add cookie signing/verification for dashboard auth"
```

---

## Task 4: Frontend Auth — Login/Logout API Routes

Create the server-side API routes for authentication.

**Files:**
- Create: `frontend/src/app/api/auth/login/route.ts`
- Create: `frontend/src/app/api/auth/logout/route.ts`

- [ ] **Step 1: Create login route**

Create `frontend/src/app/api/auth/login/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { createSessionCookie } from "@/lib/auth";

export async function POST(request: NextRequest) {
  const body = await request.json();
  const password = body.password;

  const expected = process.env.DASHBOARD_PASSWORD;
  if (!expected) {
    return NextResponse.json(
      { error: "DASHBOARD_PASSWORD not configured" },
      { status: 500 },
    );
  }

  if (password !== expected) {
    return NextResponse.json({ error: "Invalid password" }, { status: 401 });
  }

  await createSessionCookie();
  return NextResponse.json({ ok: true });
}
```

- [ ] **Step 2: Create logout route**

Create `frontend/src/app/api/auth/logout/route.ts`:

```typescript
import { NextResponse } from "next/server";
import { clearSessionCookie } from "@/lib/auth";

export async function POST() {
  await clearSessionCookie();
  return NextResponse.json({ ok: true });
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/api/auth/login/route.ts frontend/src/app/api/auth/logout/route.ts
git commit -m "feat: add login/logout API routes"
```

---

## Task 5: Frontend Auth — Middleware

Create the auth gate middleware.

**Files:**
- Create: `frontend/src/middleware.ts`

- [ ] **Step 1: Create middleware**

Create `frontend/src/middleware.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE_NAME, verifySessionCookie } from "@/lib/auth";

const PUBLIC_PATHS = ["/login", "/api/auth/"];
const IGNORED_PREFIXES = ["/_next/", "/favicon.ico"];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip static assets and Next.js internals
  if (IGNORED_PREFIXES.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Skip public paths
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Check session cookie
  const cookie = request.cookies.get(SESSION_COOKIE_NAME);
  if (cookie && (await verifySessionCookie(cookie.value))) {
    return NextResponse.next();
  }

  // Redirect to login
  const loginUrl = new URL("/login", request.url);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/middleware.ts
git commit -m "feat: add auth middleware to gate all routes behind login"
```

---

## Task 6: Frontend Auth — Login Page

Create the login page UI.

**Files:**
- Create: `frontend/src/app/login/page.tsx`

- [ ] **Step 1: Create login page**

Create `frontend/src/app/login/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      if (res.ok) {
        router.push("/");
      } else {
        const data = await res.json();
        setError(data.error || "Login failed");
      }
    } catch {
      setError("Network error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950">
      <div className="w-full max-w-sm">
        <h1 className="mb-8 text-center text-2xl font-bold tracking-tight">
          Ripken
        </h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="w-full rounded-lg border border-zinc-300 bg-white px-4 py-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
              autoFocus
            />
          </div>
          {error && (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading || !password}
            className="w-full rounded-lg bg-indigo-600 px-4 py-3 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {loading ? "..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify frontend builds**

Run: `cd frontend && npm run build 2>&1 | tail -20`

Expected: Build succeeds. Login page and API routes appear in the build output.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/login/page.tsx
git commit -m "feat: add password login page"
```

---

## Task 7: Frontend API URL Split + Hardcoded URL Fixes

Update the API client to distinguish server-side vs client-side base URLs, and fix hardcoded localhost references.

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/next.config.ts`

- [ ] **Step 1: Update api.ts with server/client URL split**

Replace the first line of `frontend/src/lib/api.ts`:

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
```

With:

```typescript
function getApiBase(): string {
  // Server-side: use internal Docker network URL if available
  if (typeof window === "undefined" && process.env.API_BASE_URL) {
    return process.env.API_BASE_URL;
  }
  // Client-side: use public URL
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

const API_BASE = getApiBase();
```

- [ ] **Step 2: Fix hardcoded Yahoo auth URL in page.tsx**

In `frontend/src/app/page.tsx`, find the hardcoded Yahoo auth link (line 206):

```tsx
href="http://localhost:8000/auth/yahoo"
```

Replace with:

```tsx
href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/auth/yahoo`}
```

Note: since `page.tsx` is a `"use client"` component, `NEXT_PUBLIC_API_URL` is available at runtime in the browser.

- [ ] **Step 3: Add standalone output to next.config.ts**

Replace the contents of `frontend/next.config.ts`:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
```

- [ ] **Step 4: Verify frontend still builds**

Run: `cd frontend && npm run build 2>&1 | tail -20`

Expected: Build succeeds. `.next/standalone` directory is created.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/app/page.tsx frontend/next.config.ts
git commit -m "feat: split API URLs for Docker, add standalone output, fix hardcoded localhost"
```

---

## Task 8: Update .env.example

Add all new environment variables to the example file.

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Update .env.example**

Add the following sections to `.env.example`:

```
# Dashboard Auth
DASHBOARD_PASSWORD=your_password_here
SESSION_SECRET=generate_a_random_64_char_string

# URLs (for production, set these to your domain)
FRONTEND_URL=http://localhost:3000
ALLOWED_ORIGINS=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:8000
# API_BASE_URL=http://backend:8000  # uncomment in Docker
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add new deployment env vars to .env.example"
```

---

## Task 9: Docker — Backend Dockerfile

Create the backend container definition.

**Files:**
- Create: `Dockerfile.backend`

- [ ] **Step 1: Create Dockerfile.backend**

Create `Dockerfile.backend` in the project root:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files and install (cached layer)
COPY pyproject.toml uv.lock ./
COPY backend/ backend/
COPY shared/ shared/
RUN uv sync --frozen --no-dev

# Create data directory (will be overridden by volume mount)
RUN mkdir -p data

EXPOSE 8000

CMD [".venv/bin/uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Note: `uv sync` installs into `.venv` by default, so the CMD uses `.venv/bin/uvicorn`.

- [ ] **Step 2: Verify it builds**

Run: `docker build -f Dockerfile.backend -t ripken-backend . 2>&1 | tail -10`

Expected: Build completes successfully.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile.backend
git commit -m "feat: add backend Dockerfile"
```

---

## Task 10: Docker — Frontend Dockerfile

Create the frontend multi-stage container definition.

**Files:**
- Create: `Dockerfile.frontend`

- [ ] **Step 1: Create Dockerfile.frontend**

Create `Dockerfile.frontend` in the project root:

```dockerfile
FROM node:22-alpine AS builder

WORKDIR /app

# Install dependencies (cached layer)
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Copy source and build
COPY frontend/ .

# Build-time env var for API URL (baked into client JS)
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# --- Production stage ---
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Copy standalone output
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
```

- [ ] **Step 2: Verify it builds**

Run:
```bash
docker build -f Dockerfile.frontend -t ripken-frontend --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 . 2>&1 | tail -10
```

Expected: Build completes successfully.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile.frontend
git commit -m "feat: add frontend Dockerfile with standalone build"
```

---

## Task 11: Docker — Caddyfile + docker-compose.yml + .dockerignore

Create the orchestration and proxy configuration.

**Files:**
- Create: `Caddyfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`

- [ ] **Step 1: Create Caddyfile**

Create `Caddyfile` in the project root:

```
{$SITE_ADDRESS:localhost} {
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

Note: Uses `SITE_ADDRESS` env var so it can be `localhost` in dev and `ripken.noahbrown.io` in production. Caddy only provisions Let's Encrypt certs when the address is a real domain (not localhost).

- [ ] **Step 2: Create docker-compose.yml**

Create `docker-compose.yml` in the project root:

```yaml
services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    environment:
      - SITE_ADDRESS=${SITE_ADDRESS:-localhost}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - backend
      - frontend

  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/app/data

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
      args:
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}
    restart: unless-stopped
    environment:
      - DASHBOARD_PASSWORD=${DASHBOARD_PASSWORD}
      - SESSION_SECRET=${SESSION_SECRET}
      - API_BASE_URL=http://backend:8000
      - NODE_ENV=production

volumes:
  caddy_data:
  caddy_config:
```

- [ ] **Step 3: Create .dockerignore**

Create `.dockerignore` in the project root:

```
.venv/
.git/
node_modules/
frontend/node_modules/
frontend/.next/
data/*.db
data/*.db-wal
data/*.db-shm
__pycache__/
*.pyc
.env
ripken.egg-info/
```

- [ ] **Step 4: Verify full stack starts**

Run:
```bash
docker compose up --build -d 2>&1 | tail -20 && sleep 5 && curl -s http://localhost/health && docker compose down
```

Expected: All three containers start. Health check returns `{"status":"ok"}`. Visiting `http://localhost` should redirect to `/login`.

- [ ] **Step 5: Commit**

```bash
git add Caddyfile docker-compose.yml .dockerignore
git commit -m "feat: add Docker Compose orchestration with Caddy reverse proxy"
```

---

## Task 12: End-to-End Verification

Verify the complete flow works locally with Docker Compose.

- [ ] **Step 1: Start the stack**

```bash
DASHBOARD_PASSWORD=testpass SESSION_SECRET=testsecret1234567890123456789012345678901234567890 docker compose up --build -d
```

Wait for all containers to be healthy.

- [ ] **Step 2: Verify login redirect**

```bash
curl -s -o /dev/null -w "%{http_code} %{redirect_url}" http://localhost/
```

Expected: `307 http://localhost/login` (Next.js middleware uses 307 Temporary Redirect).

- [ ] **Step 3: Verify login flow**

```bash
# Should fail with wrong password
curl -s -X POST http://localhost/api/auth/login -H "Content-Type: application/json" -d '{"password":"wrong"}'
```

Expected: `{"error":"Invalid password"}` with 401 status.

```bash
# Should succeed with correct password
curl -s -X POST http://localhost/api/auth/login -H "Content-Type: application/json" -d '{"password":"testpass"}' -c /tmp/ripken-cookies
```

Expected: `{"ok":true}` and a `ripken_session` cookie saved.

- [ ] **Step 4: Verify authenticated access**

```bash
curl -s -o /dev/null -w "%{http_code}" -b /tmp/ripken-cookies http://localhost/
```

Expected: `200` (dashboard page loads).

- [ ] **Step 5: Verify backend API routes**

```bash
curl -s http://localhost/health
curl -s http://localhost/api/today | head -c 200
```

Expected: Health returns `{"status":"ok"}`. Today endpoint returns game data.

- [ ] **Step 6: Tear down**

```bash
docker compose down
rm /tmp/ripken-cookies
```

- [ ] **Step 7: Commit any fixes needed**

If any issues were found and fixed during verification, commit them:

```bash
git add -A
git commit -m "fix: address issues found during Docker e2e verification"
```

---

## Task 13: VPS Provisioning Guide

Create a deployment script/checklist for the actual VPS setup (this is a reference document, not code).

**Files:**
- Create: `docs/DEPLOY.md`

- [ ] **Step 1: Write deployment guide**

Create `docs/DEPLOY.md` with the actual commands needed on the VPS:

```markdown
# Deploying Ripken to Digital Ocean

## 1. Provision Droplet

- Ubuntu 24.04, 1GB RAM / 1 vCPU ($6/mo)
- Add your SSH key during creation

## 2. Initial Server Setup

```bash
# SSH in
ssh root@<droplet-ip>

# Create swapfile (required for Next.js builds)
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Install Docker
curl -fsSL https://get.docker.com | sh

# Firewall
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw enable
```

## 3. Deploy Application

```bash
git clone https://github.com/Noah-Brown/ripken.git ~/ripken
cd ~/ripken

# Create .env (copy from .env.example, fill in production values)
cp .env.example .env
nano .env  # Set DASHBOARD_PASSWORD, SESSION_SECRET, SITE_ADDRESS, etc.

# Key production env vars:
# SITE_ADDRESS=ripken.noahbrown.io
# DASHBOARD_PASSWORD=<your-password>
# SESSION_SECRET=<generate with: openssl rand -hex 32>
# FRONTEND_URL=https://ripken.noahbrown.io
# ALLOWED_ORIGINS=https://ripken.noahbrown.io
# NEXT_PUBLIC_API_URL=https://ripken.noahbrown.io
# YAHOO_REDIRECT_URI=https://ripken.noahbrown.io/auth/yahoo/callback

docker compose up -d --build
```

## 4. DNS

Add an A record: `ripken.noahbrown.io` → `<droplet-ip>`

Caddy will automatically provision a Let's Encrypt certificate once DNS propagates.

## 5. Yahoo OAuth

1. Update redirect URI in Yahoo Developer App to `https://ripken.noahbrown.io/auth/yahoo/callback`
2. Visit `https://ripken.noahbrown.io/auth/yahoo` to authenticate

## 6. Backups

```bash
mkdir -p ~/ripken/backups

# Add cron job
cat > /etc/cron.d/ripken-backup << 'CRON'
0 4 * * * root sqlite3 /root/ripken/data/fantasy_dashboard.db ".backup /root/ripken/backups/fantasy_dashboard_$(date +\%Y\%m\%d).db" && find /root/ripken/backups -name "*.db" -mtime +7 -delete
CRON
```

## 7. Redeploying

```bash
cd ~/ripken
git pull
docker compose up -d --build
```
```

- [ ] **Step 2: Commit**

```bash
git add docs/DEPLOY.md
git commit -m "docs: add VPS deployment guide"
```
