# Bullpen Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the bullpen dashboard to match FanGraphs Roster Resource closer depth chart layout — team-grouped and flat views with daily pitch counts and season stats.

**Architecture:** Single API endpoint returns all data (season stats, daily pitches, roles). Frontend renders two togglable views from the same response. All stats computed from existing `pitcher_appearances` table.

**Tech Stack:** Python/FastAPI (backend), Next.js/React/Tailwind (frontend), SQLAlchemy async queries.

**Spec:** `docs/superpowers/specs/2026-03-28-bullpen-page-redesign-design.md`

---

### Task 1: Rework the backend bullpen API endpoint

**Files:**
- Modify: `backend/api/routes/bullpen.py`

This task replaces the current `/api/bullpen` endpoint with one that returns season stats and daily pitch counts.

- [ ] **Step 1: Add season stats query**

Add a query that aggregates all non-starter pitcher appearances grouped by player_id. This runs once and returns a dict keyed by player_id.

```python
# Season stats: G, IP, ERA, SV, HLD, K/9, K%
season_result = await db.execute(
    select(
        PitcherAppearance.player_id,
        func.count().label("g"),
        func.sum(PitcherAppearance.innings_pitched).label("ip"),
        func.sum(PitcherAppearance.earned_runs).label("er"),
        func.sum(PitcherAppearance.strikeouts).label("k"),
        func.sum(PitcherAppearance.walks).label("bb"),
        func.sum(PitcherAppearance.hits_allowed).label("h"),
        func.sum(PitcherAppearance.save).label("sv"),
        func.sum(PitcherAppearance.hold).label("hld"),
    )
    .where(PitcherAppearance.is_starter == 0)
    .group_by(PitcherAppearance.player_id)
)
```

Compute derived stats in Python:
- ERA = (er / ip) * 9 if ip > 0 else 0.0
- K/9 = (k / ip) * 9 if ip > 0 else 0.0
- K% = k / (k + bb + h) if (k + bb + h) > 0 else 0.0

Store in `season_stats: dict[int, dict]` keyed by player_id.

- [ ] **Step 2: Add daily pitches query**

Build `day_columns` as a list of 7 date strings (today back to 6 days ago). Query pitcher appearances for these dates:

```python
day_columns = [(date.today() - timedelta(days=i)).isoformat() for i in range(7)]

daily_result = await db.execute(
    select(
        PitcherAppearance.player_id,
        PitcherAppearance.date,
        PitcherAppearance.pitches,
    )
    .where(
        PitcherAppearance.is_starter == 0,
        PitcherAppearance.date >= day_columns[-1],
    )
)
```

Build `daily_by_player: dict[int, dict[str, int]]` mapping player_id -> {date: pitches}. Then for each reliever, produce `daily_pitches` array: `[daily_by_player.get(pid, {}).get(d) for d in day_columns]`.

- [ ] **Step 3: Update the response builder**

Replace the existing reliever dict construction. Remove: `usage_heatmap`, `evidence`, `appearances_last_7d`, `avg_leverage_last_14d`, `saves_last_14d`, `holds_last_14d`. Add: `season_g`, `season_ip`, `season_era`, `season_sv`, `season_hld`, `season_k9`, `season_k_pct`, `daily_pitches`.

Remove the old 14-day heatmap query (the `appearances_result` / `appearances_by_player` block).

Add `day_columns` to the top-level response dict.

- [ ] **Step 4: Verify locally**

Run: `make backend` and hit `http://localhost:8000/api/bullpen` in a browser or curl. Check that:
- `day_columns` is a 7-element array of date strings
- Each reliever has `season_g`, `season_ip`, `season_era`, `season_sv`, `season_hld`, `season_k9`, `season_k_pct`
- Each reliever has `daily_pitches` as a 7-element array of int|null

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/bullpen.py
git commit -m "feat: add season stats and daily pitches to bullpen API"
```

---

### Task 2: Rewrite the frontend bullpen page

**Files:**
- Modify: `frontend/src/app/bullpen/page.tsx`

Complete rewrite of the page component to support team-grouped and flat table views.

- [ ] **Step 1: Update TypeScript interfaces**

Replace the existing interfaces with:

```typescript
interface Reliever {
  player_id: number;
  full_name: string;
  team: string | null;
  throws: string | null;
  is_rostered: boolean;
  role: string;
  confidence: string;
  available_tonight: boolean;
  season_g: number;
  season_ip: number;
  season_era: number;
  season_sv: number;
  season_hld: number;
  season_k9: number;
  season_k_pct: number;
  daily_pitches: (number | null)[];
  pitches_last_3d: number;
  pitches_last_7d: number;
  days_since_last_appearance: number | null;
}

interface BullpenResponse {
  date: string;
  day_columns: string[];
  relievers: Reliever[];
}
```

Remove `UsageDay` interface.

- [ ] **Step 2: Add state and constants**

Keep existing: `ROLE_ORDER`, `roleBadge`, `confidenceDot`, filter state (`filterRole`, `filterTeam`, `rosterOnly`).

Add:
```typescript
const [viewMode, setViewMode] = useState<"team" | "flat">("team");
const [sortCol, setSortCol] = useState<string>("role");
const [sortAsc, setSortAsc] = useState(true);
```

Add role sort priority map:
```typescript
const ROLE_PRIORITY: Record<string, number> = {
  closer: 0, setup: 1, middle: 2, long: 3, mop_up: 4,
};
```

- [ ] **Step 3: Build the table header component**

Create a `TableHeader` component that renders column headers. The day columns should show short date labels (e.g., "3/28", "3/27"). In flat mode, clicking a column header sorts by that column.

Columns in order: Pitcher, THR, Role, G, IP, ERA, SV, HLD, K/9, K%, then 7 day columns.

- [ ] **Step 4: Build the reliever row component**

Create a `RelieverRow` component. Each row renders:
- **Pitcher**: Name with green text if `is_rostered`, team abbreviation below in small text (team-grouped mode can omit the team since it's in the header)
- **THR**: R or L
- **Role**: Color badge from `roleBadge` with confidence dot
- **Season stats**: G, IP (1 decimal), ERA (2 decimals), SV, HLD, K/9 (2 decimals), K% (formatted as .XXX like batting avg)
- **Daily pitches**: For each of 7 days, show pitch count number if not null, otherwise empty cell. Red background tint (`bg-red-100 dark:bg-red-900/30`) if pitches > 25.

- [ ] **Step 5: Build the team-grouped view**

Group relievers by team. For each team (sorted alphabetically):
- Render a team header row spanning all columns with the team abbreviation
- Render reliever rows sorted by `ROLE_PRIORITY[role]`

```typescript
const teamGroups = useMemo(() => {
  const groups: Record<string, Reliever[]> = {};
  for (const r of filteredRelievers) {
    const team = r.team || "???";
    if (!groups[team]) groups[team] = [];
    groups[team].push(r);
  }
  // Sort relievers within each team by role priority
  for (const team of Object.keys(groups)) {
    groups[team].sort((a, b) => (ROLE_PRIORITY[a.role] ?? 99) - (ROLE_PRIORITY[b.role] ?? 99));
  }
  return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
}, [filteredRelievers]);
```

- [ ] **Step 6: Build the flat table view**

Render all `filteredRelievers` in a single table. Support sorting by clicking column headers:
- Default sort: role priority, then team
- Clicking a column toggles sort direction
- Numeric columns sort numerically, text columns alphabetically

- [ ] **Step 7: Build the filter bar**

Keep existing filter dropdowns (role, team, My Relievers toggle). Add view mode toggle button:

```tsx
<button
  onClick={() => setViewMode(viewMode === "team" ? "flat" : "team")}
  className={`rounded-lg px-3 py-1.5 text-sm font-medium ...`}
>
  {viewMode === "team" ? "By Team" : "All Players"}
</button>
```

- [ ] **Step 8: Assemble the page**

Wire up the filter bar, conditional view rendering (team-grouped vs flat), loading/error states. Keep existing header/nav structure.

- [ ] **Step 9: Verify locally**

Run: `make dev` and navigate to `http://localhost:3000/bullpen`. Check:
- Team-grouped view shows teams alphabetically with relievers ordered by role
- Flat view shows all relievers in a sortable table
- Column sorting works in flat mode
- Daily pitch count columns show numbers with red tint for >25P
- Rostered players have green name highlight
- Filters (role, team, My Relievers) work in both views
- View toggle switches between modes

- [ ] **Step 10: Commit**

```bash
git add frontend/src/app/bullpen/page.tsx
git commit -m "feat: redesign bullpen page with team-grouped and flat views"
```

---

### Task 3: Deploy and verify in production

**Files:** None (deployment only)

- [ ] **Step 1: Push to remote**

```bash
git push
```

- [ ] **Step 2: Deploy to production**

```bash
ssh ripken 'cd ~/ripken && git pull && docker compose up -d --build backend'
```

Wait for backend rebuild, then also rebuild frontend if there were frontend changes:

```bash
ssh ripken 'cd ~/ripken && docker compose up -d --build frontend'
```

- [ ] **Step 3: Recompute reliever roles**

Since production already has pitcher appearances data, recompute roles so the API has data to serve:

```bash
ssh ripken 'cd ~/ripken && docker compose stop backend && cat <<'"'"'SCRIPT'"'"' | docker compose run --rm -T backend .venv/bin/python -
import asyncio
from backend.database.connection import async_session
from backend.analytics.reliever_roles import compute_reliever_roles
async def run():
    async with async_session() as db:
        n = await compute_reliever_roles(db)
        print(f"Classified {n} relievers")
asyncio.run(run())
SCRIPT'
ssh ripken 'cd ~/ripken && docker compose start backend'
```

- [ ] **Step 4: Verify production**

Open `https://ripken.noahbrown.io/bullpen` and verify both views render correctly with real data.

- [ ] **Step 5: Commit any fixes**

If any issues found during production verification, fix, commit, and redeploy.
