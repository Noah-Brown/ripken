# League-Wide Roster Tracking Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track all teams' rosters across Yahoo leagues, show ownership on the bullpen page, and add a league page with position-grouped rosters.

**Architecture:** New `league_teams` and `league_rosters` tables store all teams' data. A new hourly sync job fetches every team's roster via the Yahoo API. The bullpen API gains an optional `league_id` param for ownership lookups. A new `/league` page shows all rostered players grouped by position.

**Tech Stack:** Python/FastAPI, SQLAlchemy async, Next.js/React/Tailwind, Yahoo Fantasy API.

**Spec:** `docs/superpowers/specs/2026-03-28-league-rosters-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/database/models.py` | Modify | Add `LeagueTeam` and `LeagueRoster` models |
| `backend/yahoo/client.py` | Modify | Add `get_league_teams()` method |
| `backend/yahoo/sync.py` | Modify | Add `sync_league_rosters()` function |
| `backend/ingestion/scheduler.py` | Modify | Add hourly league roster sync job |
| `backend/api/routes/bullpen.py` | Modify | Add `league_id` param, ownership field |
| `backend/api/routes/league.py` | Create | New `/api/league/{id}/rosters` endpoint |
| `backend/main.py` | Modify | Register league router |
| `frontend/src/app/bullpen/page.tsx` | Modify | League selector, ownership indicators |
| `frontend/src/app/league/page.tsx` | Create | New league page |

---

### Task 1: Add database models

**Files:**
- Modify: `backend/database/models.py`

- [ ] **Step 1: Add LeagueTeam model**

Add after the `UserRoster` class (around line 258):

```python
class LeagueTeam(Base):
    __tablename__ = "league_teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    league_id = Column(Integer, ForeignKey("user_leagues.id"), nullable=False)
    yahoo_team_key = Column(Text, nullable=False, unique=True)
    team_name = Column(Text)
    manager_name = Column(Text)
    is_current_user = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LeagueRoster(Base):
    __tablename__ = "league_rosters"
    __table_args__ = (
        UniqueConstraint("league_id", "yahoo_team_key", "yahoo_player_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    league_id = Column(Integer, ForeignKey("user_leagues.id"), nullable=False)
    yahoo_team_key = Column(Text, nullable=False)
    yahoo_team_name = Column(Text)
    player_id = Column(Integer, ForeignKey("players.id"))
    yahoo_player_key = Column(Text, nullable=False)
    yahoo_player_name = Column(Text)
    roster_position = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 2: Lint**

Run: `ruff check backend/database/models.py`

- [ ] **Step 3: Commit**

```bash
git add backend/database/models.py
git commit -m "feat: add LeagueTeam and LeagueRoster models"
```

---

### Task 2: Add Yahoo client method for league teams

**Files:**
- Modify: `backend/yahoo/client.py`

- [ ] **Step 1: Add `get_league_teams()` method**

Add after `get_team_key()` (around line 141). This reuses the same `/league/{key}/teams` endpoint but returns all teams instead of filtering:

```python
async def get_league_teams(db: AsyncSession, league_key: str) -> list[dict]:
    """Fetch all teams in a league with metadata."""
    data = await _yahoo_get(db, f"/league/{league_key}/teams")
    teams = []
    try:
        fc = data.get("fantasy_content", data)
        league = fc.get("league", [])
        if isinstance(league, list) and len(league) > 1:
            teams_container = league[1].get("teams", {})
            for k, v in teams_container.items():
                if k == "count":
                    continue
                if isinstance(v, dict) and "team" in v:
                    team_info = v["team"]
                    if isinstance(team_info, list) and len(team_info) > 0:
                        team_meta = team_info[0]
                        if isinstance(team_meta, list):
                            entry = {}
                            for item in team_meta:
                                if isinstance(item, dict):
                                    if "team_key" in item:
                                        entry["team_key"] = item["team_key"]
                                    if "name" in item:
                                        entry["team_name"] = item["name"]
                                    if "is_owned_by_current_login" in item:
                                        entry["is_current_user"] = item["is_owned_by_current_login"] == 1
                                    if "managers" in item:
                                        mgrs = item["managers"]
                                        if isinstance(mgrs, list) and mgrs:
                                            mgr = mgrs[0].get("manager", {}) if isinstance(mgrs[0], dict) else {}
                                            entry["manager_name"] = mgr.get("nickname", "")
                                        elif isinstance(mgrs, dict):
                                            mgr = mgrs.get("0", {}).get("manager", {})
                                            entry["manager_name"] = mgr.get("nickname", "")
                            if "team_key" in entry:
                                entry.setdefault("is_current_user", False)
                                entry.setdefault("manager_name", "")
                                teams.append(entry)
    except (KeyError, IndexError, TypeError):
        logger.exception("Failed to parse league teams response.")
    return teams
```

- [ ] **Step 2: Lint**

Run: `ruff check backend/yahoo/client.py`

- [ ] **Step 3: Commit**

```bash
git add backend/yahoo/client.py
git commit -m "feat: add get_league_teams() Yahoo client method"
```

---

### Task 3: Add league roster sync

**Files:**
- Modify: `backend/yahoo/sync.py`
- Modify: `backend/ingestion/scheduler.py`

- [ ] **Step 1: Add `sync_league_rosters()` to sync.py**

Add at the end of `backend/yahoo/sync.py`:

```python
async def sync_league_rosters(db: AsyncSession) -> None:
    """Sync all teams' rosters for all connected leagues."""
    from backend.yahoo.client import get_league_teams, get_roster

    result = await db.execute(select(UserAccount).where(UserAccount.id == 1))
    account = result.scalar_one_or_none()
    if not account:
        logger.info("No Yahoo account connected — skipping league roster sync.")
        return

    result = await db.execute(select(UserLeague).where(UserLeague.user_account_id == 1))
    leagues = result.scalars().all()

    for league in leagues:
        # Fetch all teams in this league
        teams_data = await get_league_teams(db, league.yahoo_league_key)
        if not teams_data:
            logger.warning(f"No teams found for league {league.league_name}")
            continue

        # Upsert league_teams
        for t in teams_data:
            existing = await db.execute(
                select(LeagueTeam).where(LeagueTeam.yahoo_team_key == t["team_key"])
            )
            team_row = existing.scalar_one_or_none()
            if team_row:
                team_row.team_name = t.get("team_name", team_row.team_name)
                team_row.manager_name = t.get("manager_name", team_row.manager_name)
                team_row.is_current_user = 1 if t.get("is_current_user") else 0
            else:
                db.add(LeagueTeam(
                    league_id=league.id,
                    yahoo_team_key=t["team_key"],
                    team_name=t.get("team_name", ""),
                    manager_name=t.get("manager_name", ""),
                    is_current_user=1 if t.get("is_current_user") else 0,
                ))
        await db.commit()

        # Delete existing league_rosters for this league
        await db.execute(
            delete(LeagueRoster).where(LeagueRoster.league_id == league.id)
        )

        # Fetch roster for each team
        for idx, t in enumerate(teams_data):
            team_key = t["team_key"]
            team_name = t.get("team_name", "")
            logger.info(f"Fetching roster for {team_name} ({team_key})")

            yahoo_players = await get_roster(db, team_key)
            if not yahoo_players:
                continue

            # Determine league_slot for player mapping
            # Use the league's index (1 or 2) to match yahoo_id_1 or yahoo_id_2
            league_result = await db.execute(
                select(UserLeague).where(UserLeague.user_account_id == 1).order_by(UserLeague.id)
            )
            all_leagues = league_result.scalars().all()
            league_slot = next(
                (i + 1 for i, lg in enumerate(all_leagues) if lg.id == league.id), 1
            )

            matched, unmatched = await map_roster_players(db, yahoo_players, league_slot)

            for entry in matched:
                name_data = entry.get("name", {})
                yahoo_name = name_data.get("full", "") if isinstance(name_data, dict) else str(name_data)
                db.add(LeagueRoster(
                    league_id=league.id,
                    yahoo_team_key=team_key,
                    yahoo_team_name=team_name,
                    player_id=entry["internal_player_id"],
                    yahoo_player_key=entry.get("player_key", ""),
                    yahoo_player_name=yahoo_name,
                    roster_position=entry.get("selected_position", ""),
                ))

            for entry in unmatched:
                name_data = entry.get("name", {})
                yahoo_name = name_data.get("full", "") if isinstance(name_data, dict) else str(name_data)
                db.add(LeagueRoster(
                    league_id=league.id,
                    yahoo_team_key=team_key,
                    yahoo_team_name=team_name,
                    player_id=None,
                    yahoo_player_key=entry.get("player_key", ""),
                    yahoo_player_name=yahoo_name,
                    roster_position=entry.get("selected_position", ""),
                ))

            await db.commit()

            # Rate limit: 1 second between teams
            if idx < len(teams_data) - 1:
                import asyncio
                await asyncio.sleep(1)

        logger.info(f"Synced league rosters for {league.league_name}: {len(teams_data)} teams")
```

Add imports at top of sync.py:

```python
from backend.database.models import UserAccount, UserLeague, UserRoster, LeagueTeam, LeagueRoster
from sqlalchemy import delete
```

- [ ] **Step 2: Add scheduler job**

In `backend/ingestion/scheduler.py`, add the job function:

```python
async def job_sync_league_rosters():
    from backend.yahoo.sync import sync_league_rosters
    await _run_job("sync_league_rosters", sync_league_rosters)
```

Add to `create_scheduler()`:

```python
    # League-wide rosters — every hour
    scheduler.add_job(
        job_sync_league_rosters, "interval", hours=1, id="sync_league_rosters"
    )
```

- [ ] **Step 3: Lint**

Run: `ruff check backend/yahoo/sync.py backend/ingestion/scheduler.py`

- [ ] **Step 4: Commit**

```bash
git add backend/yahoo/sync.py backend/ingestion/scheduler.py
git commit -m "feat: add hourly league-wide roster sync job"
```

---

### Task 4: Update bullpen API with ownership

**Files:**
- Modify: `backend/api/routes/bullpen.py`

- [ ] **Step 1: Add `league_id` param and ownership query**

Add `league_id` query param. When provided, query `league_rosters` for that league and build an ownership map. Add `ownership` field to each reliever in the response.

After the existing roster_ids query, add:

```python
    # League ownership (when league_id provided)
    ownership_map: dict[int, dict] = {}
    if league_id is not None:
        from backend.database.models import LeagueRoster, LeagueTeam
        ownership_result = await db.execute(
            select(
                LeagueRoster.player_id,
                LeagueRoster.yahoo_team_name,
                LeagueRoster.yahoo_team_key,
            ).where(
                LeagueRoster.league_id == league_id,
                LeagueRoster.player_id.isnot(None),
            )
        )
        # Look up which team is the current user's
        user_team_keys = set()
        team_result = await db.execute(
            select(LeagueTeam.yahoo_team_key).where(
                LeagueTeam.league_id == league_id,
                LeagueTeam.is_current_user == 1,
            )
        )
        user_team_keys = {row[0] for row in team_result.all()}

        for row in ownership_result.all():
            if row.player_id is not None:
                ownership_map[row.player_id] = {
                    "team_name": row.yahoo_team_name,
                    "is_mine": row.yahoo_team_key in user_team_keys,
                }
```

Update the function signature:

```python
async def get_bullpen(
    team: str | None = Query(None),
    role: str | None = Query(None),
    roster_only: bool = Query(False),
    league_id: int | None = Query(None, description="League ID for ownership data"),
    db: AsyncSession = Depends(get_db_session),
):
```

In the reliever dict construction, add:

```python
            "ownership": ownership_map.get(pid) if league_id is not None else None,
```

Update `is_rostered` to use ownership when available:

```python
            "is_rostered": ownership_map.get(pid, {}).get("is_mine", False) if league_id is not None else (pid in roster_ids),
```

Update the roster_only filter:

```python
        if roster_only:
            if league_id is not None:
                if not ownership_map.get(pid, {}).get("is_mine", False):
                    continue
            elif pid not in roster_ids:
                continue
```

- [ ] **Step 2: Lint**

Run: `ruff check backend/api/routes/bullpen.py`

- [ ] **Step 3: Commit**

```bash
git add backend/api/routes/bullpen.py
git commit -m "feat: add league ownership to bullpen API"
```

---

### Task 5: Add league rosters API endpoint

**Files:**
- Create: `backend/api/routes/league.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Create league route**

```python
"""League-wide roster API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.database.models import LeagueRoster, LeagueTeam, Player, UserLeague

router = APIRouter(prefix="/api", tags=["league"])

POSITION_ORDER = ["C", "1B", "2B", "SS", "3B", "OF", "Util", "SP", "RP", "BN", "DL", "IL", "IL+", "NA"]


@router.get("/league/{league_id}/rosters")
async def get_league_rosters(
    league_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """All rostered players in a league, grouped by position."""
    # Get league info
    league_result = await db.execute(
        select(UserLeague).where(UserLeague.id == league_id)
    )
    league = league_result.scalar_one_or_none()
    if not league:
        return {"error": "League not found"}

    # Get teams
    teams_result = await db.execute(
        select(LeagueTeam).where(LeagueTeam.league_id == league_id)
    )
    teams = [
        {
            "yahoo_team_key": t.yahoo_team_key,
            "team_name": t.team_name,
            "is_current_user": bool(t.is_current_user),
        }
        for t in teams_result.scalars().all()
    ]

    # Get all roster entries with player data
    roster_result = await db.execute(
        select(LeagueRoster, Player)
        .outerjoin(Player, LeagueRoster.player_id == Player.id)
        .where(LeagueRoster.league_id == league_id)
        .order_by(LeagueRoster.roster_position, LeagueRoster.yahoo_player_name)
    )

    # Build user team keys for highlighting
    user_team_keys = {t["yahoo_team_key"] for t in teams if t["is_current_user"]}

    # Group by position
    positions: dict[str, list] = {}
    for lr, player in roster_result.all():
        pos = lr.roster_position or "BN"
        if pos not in positions:
            positions[pos] = []
        positions[pos].append({
            "player_id": player.id if player else None,
            "player_name": player.full_name if player else lr.yahoo_player_name,
            "team": player.team if player else None,
            "owner": lr.yahoo_team_name,
            "is_current_user": lr.yahoo_team_key in user_team_keys,
        })

    # Sort positions by defined order
    ordered = {}
    for pos in POSITION_ORDER:
        if pos in positions:
            ordered[pos] = positions[pos]
    # Append any positions not in the predefined order
    for pos in positions:
        if pos not in ordered:
            ordered[pos] = positions[pos]

    return {
        "league_name": league.league_name,
        "teams": teams,
        "positions": ordered,
    }
```

- [ ] **Step 2: Register router in main.py**

In `backend/main.py`, add the import and include:

```python
from backend.api.routes.league import router as league_router
app.include_router(league_router)
```

Follow the same pattern as existing router registrations.

- [ ] **Step 3: Lint**

Run: `ruff check backend/api/routes/league.py backend/main.py`

- [ ] **Step 4: Commit**

```bash
git add backend/api/routes/league.py backend/main.py
git commit -m "feat: add league rosters API endpoint"
```

---

### Task 6: Update bullpen frontend with league selector and ownership

**Files:**
- Modify: `frontend/src/app/bullpen/page.tsx`

- [ ] **Step 1: Add league state and fetch**

Import `LeagueInfo` from `@/lib/api`. Add state:

```typescript
const [leagues, setLeagues] = useState<LeagueInfo[]>([]);
const [selectedLeague, setSelectedLeague] = useState<number | null>(null);
```

Add useEffect to fetch leagues on mount:

```typescript
useEffect(() => {
  fetchApi<{ leagues: LeagueInfo[] }>("/api/leagues")
    .then((data) => setLeagues(data.leagues))
    .catch(() => {});
}, []);
```

Update the bullpen fetch to include `league_id`:

```typescript
if (selectedLeague) params.set("league_id", String(selectedLeague));
```

Add `selectedLeague` to the useEffect dependency array.

- [ ] **Step 2: Update Reliever interface**

Add to the interface:

```typescript
  ownership: { team_name: string; is_mine: boolean } | null;
```

- [ ] **Step 3: Update roster indicators in RelieverRow**

Replace the green dot logic with three-state ownership:

```tsx
{r.ownership?.is_mine && (
  <span
    className="h-1.5 w-1.5 rounded-full bg-green-500 flex-shrink-0"
    title="On your roster"
  />
)}
{r.ownership && !r.ownership.is_mine && (
  <span
    className="h-1.5 w-1.5 rounded-full bg-amber-500 flex-shrink-0"
    title={r.ownership.team_name}
  />
)}
```

When no league is selected, fall back to the existing `is_rostered` boolean:

```tsx
{!r.ownership && r.is_rostered && (
  <span
    className="h-1.5 w-1.5 rounded-full bg-green-500 flex-shrink-0"
    title="On your roster"
  />
)}
```

- [ ] **Step 4: Add league dropdown to filter bar**

Add before the role dropdown:

```tsx
{leagues.length > 0 && (
  <select
    value={selectedLeague ?? ""}
    onChange={(e) => setSelectedLeague(e.target.value ? Number(e.target.value) : null)}
    className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800"
  >
    <option value="">No League</option>
    {leagues.map((lg) => (
      <option key={lg.id} value={lg.id}>{lg.name}</option>
    ))}
  </select>
)}
```

- [ ] **Step 5: Update My Relievers filter**

Update the rosterOnly filter logic to work with ownership:

```typescript
// In the filter bar button, use ownership.is_mine when league selected
```

The backend already handles this via the `roster_only` + `league_id` params.

- [ ] **Step 6: Build and verify**

Run: `cd frontend && npx next build`
Expected: Build succeeds, `/bullpen` page compiles.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/bullpen/page.tsx
git commit -m "feat: add league selector and ownership indicators to bullpen page"
```

---

### Task 7: Create league page frontend

**Files:**
- Create: `frontend/src/app/league/page.tsx`

- [ ] **Step 1: Create the page**

```tsx
"use client";

import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { fetchApi } from "@/lib/api";
import type { LeagueInfo } from "@/lib/api";

interface RosterPlayer {
  player_id: number | null;
  player_name: string;
  team: string | null;
  owner: string;
  is_current_user: boolean;
}

interface LeagueRostersResponse {
  league_name: string;
  teams: { yahoo_team_key: string; team_name: string; is_current_user: boolean }[];
  positions: Record<string, RosterPlayer[]>;
}

export default function LeaguePage() {
  const [leagues, setLeagues] = useState<LeagueInfo[]>([]);
  const [selectedLeague, setSelectedLeague] = useState<number | null>(null);
  const [data, setData] = useState<LeagueRostersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortCol, setSortCol] = useState<"player" | "owner">("player");
  const [sortAsc, setSortAsc] = useState(true);

  useEffect(() => {
    fetchApi<{ leagues: LeagueInfo[] }>("/api/leagues")
      .then((res) => {
        setLeagues(res.leagues);
        if (res.leagues.length > 0) setSelectedLeague(res.leagues[0].id);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedLeague) return;
    setError(null);
    fetchApi<LeagueRostersResponse>(`/api/league/${selectedLeague}/rosters`)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [selectedLeague]);

  function handleSort(col: "player" | "owner") {
    if (sortCol === col) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(true); }
  }

  function sortPlayers(players: RosterPlayer[]): RosterPlayer[] {
    return [...players].sort((a, b) => {
      const va = sortCol === "player" ? a.player_name : a.owner;
      const vb = sortCol === "player" ? b.player_name : b.owner;
      const cmp = va.localeCompare(vb);
      return sortAsc ? cmp : -cmp;
    });
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950">
      <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-2xl font-bold tracking-tight hover:opacity-80">Ripken</Link>
            <span className="text-sm text-zinc-400 dark:text-zinc-500">/</span>
            <span className="text-sm font-medium">League Rosters</span>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/roster" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Roster</Link>
            <Link href="/bullpen" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Bullpen</Link>
            <Link href="/lineups" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Lineups</Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        {/* League selector */}
        <div className="mb-6 flex items-center gap-3">
          {leagues.length > 0 && (
            <select
              value={selectedLeague ?? ""}
              onChange={(e) => setSelectedLeague(Number(e.target.value))}
              className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-800"
            >
              {leagues.map((lg) => (
                <option key={lg.id} value={lg.id}>{lg.name}</option>
              ))}
            </select>
          )}
        </div>

        {error && (
          <p className="mb-4 rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>
        )}

        {!data && !error && <p className="text-zinc-500 dark:text-zinc-400">Loading...</p>}

        {data && Object.entries(data.positions).map(([pos, players]) => (
          <Fragment key={pos}>
            <div className="mt-6 mb-2">
              <h2 className="text-sm font-bold text-zinc-600 dark:text-zinc-300">{pos}</h2>
            </div>
            <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800 mb-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
                    <th
                      className="px-3 py-2 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400 cursor-pointer select-none"
                      onClick={() => handleSort("player")}
                    >
                      Player {sortCol === "player" && (sortAsc ? "\u25B2" : "\u25BC")}
                    </th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400">Team</th>
                    <th
                      className="px-3 py-2 text-left text-xs font-medium text-zinc-500 dark:text-zinc-400 cursor-pointer select-none"
                      onClick={() => handleSort("owner")}
                    >
                      Owner {sortCol === "owner" && (sortAsc ? "\u25B2" : "\u25BC")}
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-zinc-900">
                  {sortPlayers(players).map((p, i) => (
                    <tr key={`${p.player_name}-${i}`} className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50">
                      <td className={`px-3 py-2 text-sm font-medium ${p.is_current_user ? "text-green-600 dark:text-green-400" : ""}`}>
                        {p.player_name}
                      </td>
                      <td className="px-3 py-2 text-xs text-zinc-500 dark:text-zinc-400">{p.team || "—"}</td>
                      <td className="px-3 py-2 text-xs text-zinc-500 dark:text-zinc-400">{p.owner}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Fragment>
        ))}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Build and verify**

Run: `cd frontend && npx next build`
Expected: Build succeeds, `/league` page compiles.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/league/page.tsx
git commit -m "feat: add league page with position-grouped rosters"
```

---

### Task 8: Deploy and verify in production

**Files:** None (deployment only)

- [ ] **Step 1: Push**

```bash
git push
```

- [ ] **Step 2: Deploy**

```bash
ssh ripken 'cd ~/ripken && git pull && docker compose up -d --build backend frontend'
```

- [ ] **Step 3: Add new tables to production DB**

The new tables need to be created since `create_all` at startup should handle them. Verify by checking backend logs:

```bash
ssh ripken 'cd ~/ripken && docker compose logs backend --tail 10'
```

If tables weren't created, run manually:

```bash
ssh ripken 'cd ~/ripken && docker compose stop backend && echo "..." | docker compose run --rm -T backend .venv/bin/python -'
```

- [ ] **Step 4: Trigger initial league roster sync**

Run the sync manually since the hourly job won't fire immediately:

```bash
ssh ripken 'cd ~/ripken && docker compose stop backend && echo "import asyncio
from backend.database.connection import async_session
from backend.yahoo.sync import sync_league_rosters
async def run():
    async with async_session() as db:
        await sync_league_rosters(db)
asyncio.run(run())" | docker compose run --rm -T backend .venv/bin/python - && docker compose start backend'
```

- [ ] **Step 5: Verify production**

- Open `https://ripken.noahbrown.io/bullpen` — league dropdown should appear, ownership dots should show
- Open `https://ripken.noahbrown.io/league` — position-grouped rosters should display
