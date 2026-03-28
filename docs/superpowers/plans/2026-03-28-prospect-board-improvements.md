# Prospect Board Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the FanGraphs CSV import to capture all columns, add FV badges, a slide-out detail panel with scouting reports, and real-time MiLB stats from the MLB Stats API.

**Architecture:** Backend-first approach — extend the DB schema, fix the CSV import, add a stats-fetching endpoint, then update the frontend to display FV badges and the slide-out panel. The MLB Stats API is free and unauthenticated. Stats are cached in the DB with a 6-hour TTL.

**Tech Stack:** Python/FastAPI, SQLAlchemy (async, SQLite), httpx, Next.js 14 (React 19), Tailwind CSS v4

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/database/models.py` | Modify | Add new columns to `Prospect`, add `fangraphs_id_str` to `Player` |
| `backend/api/routes/prospects.py` | Modify | Fix CSV import mapping, add re-import (update) logic, add `GET /api/prospects/{id}/stats` endpoint, include new fields in response |
| `backend/analytics/prospect_signals.py` | Modify | Include new fields (fv, scouting_report, physical profile, video_url) in signal response |
| `backend/ingestion/mlb_stats_api.py` | Create | MiLB stats fetcher — resolves MLB ID, fetches season stats, returns structured data |
| `frontend/src/app/prospects/page.tsx` | Modify | Add FV column, clickable rows, slide-out detail panel with all sections |

---

### Task 1: Add New Database Columns

**Files:**
- Modify: `backend/database/models.py:25-43` (Player model)
- Modify: `backend/database/models.py:183-199` (Prospect model)

- [ ] **Step 1: Add `fangraphs_id_str` to Player model**

In `backend/database/models.py`, add a new column after line 33 (`fangraphs_id`):

```python
fangraphs_id_str = Column(Text)  # FanGraphs prospect ID string (e.g. "sa3065496")
```

- [ ] **Step 2: Add new columns to Prospect model**

In `backend/database/models.py`, add these columns after `minor_league_stats` (line 198):

```python
fv = Column(Integer)  # FanGraphs Future Value (20-80 scale)
scouting_report = Column(Text)  # Full FanGraphs scouting report
video_url = Column(Text)
trend = Column(Text)
redraft_rank = Column(Integer)
age = Column(Text)
height = Column(Text)
weight = Column(Text)
stats_fetched_at = Column(DateTime)
```

- [ ] **Step 3: Verify the app starts and creates the new columns**

Run: `cd /home/nbrown/projects/ripken/.claude/worktrees/tidy-herding-dream && make backend`

Expected: Server starts without errors. SQLite `create_all` adds the new columns to existing tables. Kill the server after verifying startup.

- [ ] **Step 4: Commit**

```bash
git add backend/database/models.py
git commit -m "feat: add prospect detail columns to database schema

Add fv, scouting_report, video_url, trend, redraft_rank, age, height,
weight, stats_fetched_at to Prospect. Add fangraphs_id_str to Player."
```

---

### Task 2: Fix CSV Import Column Mapping

**Files:**
- Modify: `backend/api/routes/prospects.py:127-200`

- [ ] **Step 1: Update the import endpoint to map all FanGraphs columns**

Replace the entire `import_prospects_csv` function (lines 127-200) in `backend/api/routes/prospects.py` with:

```python
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

        # Parse numeric fields
        try:
            rank = int(rank_str) if rank_str else None
        except ValueError:
            rank = None
        try:
            redraft_rank = int(redraft_rank_str) if redraft_rank_str else None
        except ValueError:
            redraft_rank = None
        try:
            fv = int(fv_str) if fv_str else None
        except ValueError:
            fv = None

        # Find or create player
        result = await db.execute(
            select(Player).where(Player.full_name == name.strip())
        )
        player = result.scalar_one_or_none()

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
```

- [ ] **Step 2: Verify import works with the real CSV**

Copy the FanGraphs CSV to the project directory and test with curl:

```bash
curl -X POST http://localhost:8000/api/prospects/import \
  -F "file=@/mnt/c/Users/noahb/Downloads/fangraphs-the-board.csv"
```

Expected: `{"imported": <N>, "updated": 0, "skipped": 0}` where N matches the number of rows in the CSV.

- [ ] **Step 3: Verify re-import updates existing records**

Run the same curl command again.

Expected: `{"imported": 0, "updated": <N>, "skipped": 0}` — all records updated, none duplicated.

- [ ] **Step 4: Commit**

```bash
git add backend/api/routes/prospects.py
git commit -m "feat: fix CSV import to map all FanGraphs 'The Board' columns

Maps Current Level, Dynasty Rank, Re-Draft Rank, FV, Report, Video,
PlayerId, Age, Ht, Wt, B, T. Re-importing updates existing records
instead of skipping."
```

---

### Task 3: Add New Fields to Prospect Signal Response

**Files:**
- Modify: `backend/analytics/prospect_signals.py:106-130`

- [ ] **Step 1: Add new fields to the scored prospect dict**

In `backend/analytics/prospect_signals.py`, update the dict in the `scored.append({...})` block (lines 106-130). Add these fields after `"scouting_notes"` (line 117):

```python
"fv": prospect.fv,
"scouting_report": prospect.scouting_report,
"video_url": prospect.video_url,
"trend": prospect.trend,
"redraft_rank": prospect.redraft_rank,
"age": prospect.age,
"height": prospect.height,
"weight": prospect.weight,
"bats": player.bats,
"throws": player.throws,
```

- [ ] **Step 2: Verify the API returns new fields**

```bash
curl -s http://localhost:8000/api/prospects | python3 -m json.tool | head -40
```

Expected: Each prospect object now includes `fv`, `scouting_report`, `video_url`, `trend`, `redraft_rank`, `age`, `height`, `weight`, `bats`, `throws`.

- [ ] **Step 3: Commit**

```bash
git add backend/analytics/prospect_signals.py
git commit -m "feat: include FV, scouting report, and physical profile in prospect API response"
```

---

### Task 4: Create MiLB Stats Fetcher

**Files:**
- Create: `backend/ingestion/mlb_stats_api.py`

- [ ] **Step 1: Create the MiLB stats fetcher module**

Create `backend/ingestion/mlb_stats_api.py`:

```python
"""MiLB stats fetcher using the MLB Stats API.

Resolves player MLB IDs and fetches current minor league season stats.
The MLB Stats API is free and requires no authentication.
"""

import logging
from datetime import datetime

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

# Minor league sport IDs in the MLB Stats API
MILB_SPORT_IDS = {
    11: "AAA",
    12: "AA",
    13: "High-A",
    14: "A",
    15: "Short-A",
    16: "Rookie",
}

HITTING_FIELDS = ["avg", "ops", "homeRuns", "stolenBases", "strikeOuts",
                  "baseOnBalls", "plateAppearances", "gamesPlayed",
                  "atBats", "hits"]
PITCHING_FIELDS = ["era", "whip", "strikeoutsPer9Inn", "walksPer9Inn",
                   "inningsPitched", "gamesPlayed", "wins", "losses",
                   "saves", "hits", "earnedRuns"]


async def resolve_mlb_id(player_name: str) -> int | None:
    """Search the MLB Stats API for a player by name and return their MLB ID."""
    url = f"{settings.mlb_stats_api_base}/people/search"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params={"names": player_name})
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, Exception) as e:
        logger.warning(f"MLB API search failed for '{player_name}': {e}")
        return None

    people = data.get("people", [])
    if not people:
        return None

    # Prefer exact name match; fall back to first result
    for person in people:
        full = person.get("fullName", "")
        if full.lower() == player_name.lower():
            return person.get("id")
    return people[0].get("id")


async def fetch_milb_stats(mlb_id: int, season: int | None = None) -> list[dict]:
    """Fetch minor league season stats for a player from the MLB Stats API.

    Returns a list of stat entries, one per minor league level the player
    appeared at during the season. Each entry has 'level', 'sport_id',
    and either 'hitting' or 'pitching' (or both).
    """
    if season is None:
        season = datetime.now().year

    sport_ids = ",".join(str(sid) for sid in MILB_SPORT_IDS)
    base = settings.mlb_stats_api_base

    results_by_level: dict[int, dict] = {}

    for group in ("hitting", "pitching"):
        url = (
            f"{base}/people/{mlb_id}/stats"
            f"?stats=season&season={season}&gameType=R"
            f"&group={group}&sportId={sport_ids}"
        )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, Exception) as e:
            logger.warning(f"MLB API stats fetch failed for mlb_id={mlb_id} group={group}: {e}")
            continue

        for split_group in data.get("stats", []):
            for split in split_group.get("splits", []):
                sport = split.get("sport", {})
                sport_id = sport.get("id")
                if sport_id not in MILB_SPORT_IDS:
                    continue

                stat = split.get("stat", {})
                if not stat:
                    continue

                entry = results_by_level.setdefault(sport_id, {
                    "level": MILB_SPORT_IDS[sport_id],
                    "sport_id": sport_id,
                    "hitting": None,
                    "pitching": None,
                })

                if group == "hitting":
                    pa = int(stat.get("plateAppearances", 0))
                    ab = int(stat.get("atBats", 0))
                    k_pct = f"{(int(stat.get('strikeOuts', 0)) / pa * 100):.1f}%" if pa else "0.0%"
                    bb_pct = f"{(int(stat.get('baseOnBalls', 0)) / pa * 100):.1f}%" if pa else "0.0%"
                    entry["hitting"] = {
                        "avg": stat.get("avg", ".000"),
                        "ops": stat.get("ops", ".000"),
                        "hr": int(stat.get("homeRuns", 0)),
                        "sb": int(stat.get("stolenBases", 0)),
                        "k_pct": k_pct,
                        "bb_pct": bb_pct,
                        "pa": pa,
                        "games": int(stat.get("gamesPlayed", 0)),
                    }
                else:
                    entry["pitching"] = {
                        "era": stat.get("era", "0.00"),
                        "whip": stat.get("whip", "0.00"),
                        "k_per_9": stat.get("strikeoutsPer9Inn", "0.00"),
                        "bb_per_9": stat.get("walksPer9Inn", "0.00"),
                        "ip": stat.get("inningsPitched", "0.0"),
                        "games": int(stat.get("gamesPlayed", 0)),
                    }

    # Sort by level (AAA first)
    return sorted(results_by_level.values(), key=lambda x: x["sport_id"])
```

- [ ] **Step 2: Commit**

```bash
git add backend/ingestion/mlb_stats_api.py
git commit -m "feat: add MiLB stats fetcher using MLB Stats API

Resolves MLB IDs via name search and fetches minor league season stats
broken down by level. Supports both hitting and pitching stat groups."
```

---

### Task 5: Add Prospect Stats API Endpoint

**Files:**
- Modify: `backend/api/routes/prospects.py`

- [ ] **Step 1: Add the stats endpoint**

At the top of `backend/api/routes/prospects.py`, add these imports:

```python
from datetime import datetime, timedelta, timezone

from backend.ingestion.mlb_stats_api import fetch_milb_stats, resolve_mlb_id
```

Then add this new route after the `remove_prospect` function (after line 124):

```python
@router.get("/api/prospects/{prospect_id}/stats")
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
```

- [ ] **Step 2: Test the endpoint**

First, make sure you have prospects imported, then test:

```bash
curl -s http://localhost:8000/api/prospects/1/stats | python3 -m json.tool
```

Expected: Returns stats with resolved MLB ID, or an error message if the player isn't found in the MLB Stats API. The `stats` array contains level-by-level hitting/pitching data.

- [ ] **Step 3: Test cache behavior**

Run the same curl command again immediately.

Expected: Response includes `"cached": true` and returns instantly.

- [ ] **Step 4: Commit**

```bash
git add backend/api/routes/prospects.py
git commit -m "feat: add GET /api/prospects/{id}/stats endpoint

Fetches MiLB stats from MLB Stats API with 6-hour cache. Resolves MLB
IDs via name search and caches them on the player record."
```

---

### Task 6: Frontend — Add FV Column and Clickable Rows

**Files:**
- Modify: `frontend/src/app/prospects/page.tsx`

- [ ] **Step 1: Update the ProspectEntry interface**

In `frontend/src/app/prospects/page.tsx`, update the `ProspectEntry` interface (lines 26-43) to add the new fields:

```typescript
interface ProspectEntry {
  prospect_id: number;
  player_id: number;
  full_name: string;
  org: string;
  level: string | null;
  position: string | null;
  user_rank: number | null;
  fangraphs_rank: number | null;
  eta: string | null;
  on_40_man: boolean;
  scouting_notes: string | null;
  minor_league_stats: Record<string, unknown> | null;
  signal_score: number;
  signal: "hot" | "warm" | "cold";
  factors: ProspectFactors;
  buzz: BuzzItem[];
  // New fields
  fv: number | null;
  scouting_report: string | null;
  video_url: string | null;
  trend: string | null;
  redraft_rank: number | null;
  age: string | null;
  height: string | null;
  weight: string | null;
  bats: string | null;
  throws: string | null;
}
```

- [ ] **Step 2: Add the FvBadge component**

Add this component after the `BuzzTooltip` component (after line 111):

```tsx
function FvBadge({ fv }: { fv: number | null }) {
  if (fv == null) return <span className="text-xs text-zinc-400">—</span>;
  const intensity =
    fv >= 70
      ? "bg-indigo-600 text-white"
      : fv >= 55
        ? "bg-indigo-500 text-white"
        : fv >= 45
          ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300"
          : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${intensity}`}>
      FV {fv}
    </span>
  );
}
```

- [ ] **Step 3: Update ProspectRow to accept onClick and add FV column**

Update the `ProspectRow` component to accept an `onClick` prop and add the FV cell. Replace the entire `ProspectRow` function (lines 113-192):

```tsx
function ProspectRow({ p, onClick }: { p: ProspectEntry; onClick: () => void }) {
  const signal = signalColors[p.signal];

  return (
    <tr
      className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/50 cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors"
      onClick={onClick}
    >
      <td className="px-3 py-3 text-center">
        <span className="text-sm font-mono text-zinc-400">
          {p.user_rank ?? p.fangraphs_rank ?? "—"}
        </span>
      </td>
      <td className="px-3 py-3">
        <FvBadge fv={p.fv} />
      </td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${signal.dot}`} />
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${signal.bg} ${signal.text}`}>
            {p.signal_score}
          </span>
        </div>
      </td>
      <td className="px-3 py-3">
        <div>
          <span className="font-medium">{p.full_name}</span>
          {p.position && (
            <span className="ml-1.5 text-xs text-zinc-400">{p.position}</span>
          )}
        </div>
      </td>
      <td className="px-3 py-3 text-xs text-zinc-500">{p.org}</td>
      <td className="px-3 py-3 text-xs text-zinc-500">{p.level ?? "—"}</td>
      <td className="px-3 py-3 text-center">
        {p.on_40_man ? (
          <span className="text-xs font-medium text-green-600 dark:text-green-400">Yes</span>
        ) : (
          <span className="text-xs text-zinc-400">No</span>
        )}
      </td>
      <td className="px-3 py-3 text-xs text-zinc-500">{p.eta ?? "—"}</td>
      <td className="px-3 py-3">
        <BuzzBadge count={p.buzz.length} />
      </td>
    </tr>
  );
}
```

- [ ] **Step 4: Update the table header to include FV column**

Replace the `<thead>` block (lines 307-318) with:

```tsx
<thead>
  <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900/50">
    <th className="px-3 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400 w-12">Rank</th>
    <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">FV</th>
    <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">Signal</th>
    <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400">Player</th>
    <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">Org</th>
    <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-16">Level</th>
    <th className="px-3 py-2 text-center font-medium text-zinc-500 dark:text-zinc-400 w-16">40-Man</th>
    <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-20">ETA</th>
    <th className="px-3 py-2 text-left font-medium text-zinc-500 dark:text-zinc-400 w-24">Buzz</th>
  </tr>
</thead>
```

- [ ] **Step 5: Add selected prospect state and update row rendering**

In the `ProspectsPage` component, add state for the selected prospect (after line 200):

```tsx
const [selectedProspect, setSelectedProspect] = useState<ProspectEntry | null>(null);
```

Update the row rendering in the `<tbody>` (replace lines 320-323):

```tsx
<tbody className="bg-white dark:bg-zinc-900">
  {prospects.map((p) => (
    <ProspectRow
      key={p.prospect_id}
      p={p}
      onClick={() => setSelectedProspect(p)}
    />
  ))}
</tbody>
```

- [ ] **Step 6: Remove the old MiLB Stats column from the table**

The MiLB Stats column has been removed from the table header (Step 4) and the row (Step 3). The old `BuzzTooltip` inline expand in `ProspectRow` has also been removed — buzz will now appear in the detail panel.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/prospects/page.tsx
git commit -m "feat: add FV column and clickable rows to prospect table

Displays FV badge with color intensity by grade. Rows are clickable
with hover state. Removed inline MiLB stats column (moving to detail
panel). Tracks selected prospect in state."
```

---

### Task 7: Frontend — Slide-out Detail Panel

**Files:**
- Modify: `frontend/src/app/prospects/page.tsx`

- [ ] **Step 1: Add the MiLB stats response type**

Add this interface after the `ProspectsResponse` interface:

```typescript
interface MilbStatsLevel {
  level: string;
  sport_id: number;
  hitting: {
    avg: string;
    ops: string;
    hr: number;
    sb: number;
    k_pct: string;
    bb_pct: string;
    pa: number;
    games: number;
  } | null;
  pitching: {
    era: string;
    whip: string;
    k_per_9: string;
    bb_per_9: string;
    ip: string;
    games: number;
  } | null;
}

interface MilbStatsResponse {
  player_id: number;
  mlb_id: number | null;
  season: number;
  stats: MilbStatsLevel[];
  cached?: boolean;
  error?: string;
}
```

- [ ] **Step 2: Create the ProspectDetailPanel component**

Add this component after the `FvBadge` component:

```tsx
function ProspectDetailPanel({
  prospect,
  onClose,
}: {
  prospect: ProspectEntry;
  onClose: () => void;
}) {
  const [stats, setStats] = useState<MilbStatsResponse | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const signal = signalColors[prospect.signal];

  useEffect(() => {
    setStatsLoading(true);
    fetchApi<MilbStatsResponse>(`/api/prospects/${prospect.prospect_id}/stats`)
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setStatsLoading(false));
  }, [prospect.prospect_id]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleEsc);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleEsc);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  const factorLabels: Record<string, string> = {
    performance: "Performance",
    roster_need: "Roster Need",
    proximity: "Proximity",
    forty_man: "40-Man",
    service_time: "Service Time",
    buzz: "Buzz",
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30 dark:bg-black/50"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative w-full max-w-2xl overflow-y-auto bg-white shadow-xl dark:bg-zinc-900 animate-slide-in">
        {/* Header */}
        <div className="sticky top-0 z-10 border-b border-zinc-200 bg-white px-6 py-4 dark:border-zinc-800 dark:bg-zinc-900">
          <button
            onClick={onClose}
            className="absolute right-4 top-4 rounded-lg p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>

          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold">{prospect.full_name}</h2>
            <FvBadge fv={prospect.fv} />
          </div>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            {[prospect.position, prospect.org, prospect.level, prospect.eta ? `ETA ${prospect.eta}` : null]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>

        <div className="space-y-6 px-6 py-5">
          {/* Physical Profile */}
          {(prospect.age || prospect.height || prospect.weight || prospect.bats) && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 rounded-lg bg-zinc-50 px-4 py-2.5 text-sm text-zinc-600 dark:bg-zinc-800/50 dark:text-zinc-400">
              {prospect.age && <span>Age: <span className="font-medium text-zinc-800 dark:text-zinc-200">{prospect.age}</span></span>}
              {prospect.height && <span>Ht: <span className="font-medium text-zinc-800 dark:text-zinc-200">{prospect.height}</span></span>}
              {prospect.weight && <span>Wt: <span className="font-medium text-zinc-800 dark:text-zinc-200">{prospect.weight} lbs</span></span>}
              {(prospect.bats || prospect.throws) && (
                <span>B/T: <span className="font-medium text-zinc-800 dark:text-zinc-200">{prospect.bats ?? "?"}/{prospect.throws ?? "?"}</span></span>
              )}
            </div>
          )}

          {/* Signal Score */}
          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${signal.dot}`} />
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${signal.bg} ${signal.text}`}>
                {signal.label} {prospect.signal_score}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(prospect.factors).map(([key, value]) => (
                <div key={key} className="rounded-md bg-zinc-50 px-3 py-2 dark:bg-zinc-800/50">
                  <div className="text-[10px] text-zinc-500 dark:text-zinc-400">{factorLabels[key] ?? key}</div>
                  <div className="mt-0.5 flex items-center gap-2">
                    <div className="h-1.5 flex-1 rounded-full bg-zinc-200 dark:bg-zinc-700">
                      <div
                        className="h-1.5 rounded-full bg-indigo-500"
                        style={{ width: `${value}%` }}
                      />
                    </div>
                    <span className="text-[10px] font-mono text-zinc-500">{value}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* MiLB Stats */}
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              MiLB Stats ({new Date().getFullYear()} Season)
            </h3>
            {statsLoading ? (
              <p className="text-sm text-zinc-400">Loading stats...</p>
            ) : stats?.error ? (
              <p className="text-sm text-zinc-400">{stats.error}</p>
            ) : stats && stats.stats.length > 0 ? (
              <div className="space-y-3">
                {stats.stats.map((level) => (
                  <div key={level.sport_id}>
                    <div className="mb-1 text-[10px] font-semibold text-zinc-500 dark:text-zinc-400">{level.level}</div>
                    {level.hitting && (
                      <div className="grid grid-cols-4 gap-2">
                        {([
                          ["AVG", level.hitting.avg],
                          ["OPS", level.hitting.ops],
                          ["HR", level.hitting.hr],
                          ["SB", level.hitting.sb],
                          ["K%", level.hitting.k_pct],
                          ["BB%", level.hitting.bb_pct],
                          ["PA", level.hitting.pa],
                          ["G", level.hitting.games],
                        ] as [string, string | number][]).map(([label, val]) => (
                          <div key={label} className="rounded-md bg-zinc-50 px-2 py-1.5 text-center dark:bg-zinc-800/50">
                            <div className="text-sm font-bold">{val}</div>
                            <div className="text-[9px] text-zinc-400">{label}</div>
                          </div>
                        ))}
                      </div>
                    )}
                    {level.pitching && (
                      <div className="grid grid-cols-3 gap-2">
                        {([
                          ["ERA", level.pitching.era],
                          ["WHIP", level.pitching.whip],
                          ["K/9", level.pitching.k_per_9],
                          ["BB/9", level.pitching.bb_per_9],
                          ["IP", level.pitching.ip],
                          ["G", level.pitching.games],
                        ] as [string, string | number][]).map(([label, val]) => (
                          <div key={label} className="rounded-md bg-zinc-50 px-2 py-1.5 text-center dark:bg-zinc-800/50">
                            <div className="text-sm font-bold">{val}</div>
                            <div className="text-[9px] text-zinc-400">{label}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-zinc-400">No minor league stats available</p>
            )}
          </div>

          {/* Scouting Report */}
          {prospect.scouting_report && (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Scouting Report
              </h3>
              <div className="max-h-96 overflow-y-auto rounded-lg bg-zinc-50 px-4 py-3 text-sm leading-relaxed text-zinc-700 dark:bg-zinc-800/50 dark:text-zinc-300">
                {prospect.scouting_report.split("\n").map((paragraph, i) => (
                  <p key={i} className={i > 0 ? "mt-3" : ""}>
                    {paragraph}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Buzz */}
          {prospect.buzz.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                Recent Buzz
              </h3>
              <BuzzTooltip items={prospect.buzz} />
            </div>
          )}

          {/* Video */}
          {prospect.video_url && (
            <div>
              <a
                href={prospect.video_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Watch Video
              </a>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add the slide-in animation CSS**

Add a `<style>` tag inside the `ProspectsPage` return, at the top of the outer `<div>` (before the `<header>`):

```tsx
<style jsx global>{`
  @keyframes slide-in {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
  }
  .animate-slide-in {
    animation: slide-in 0.2s ease-out;
  }
`}</style>
```

- [ ] **Step 4: Render the detail panel**

Add the panel rendering at the end of the `<main>` tag, just before the closing `</main>`:

```tsx
{selectedProspect && (
  <ProspectDetailPanel
    prospect={selectedProspect}
    onClose={() => setSelectedProspect(null)}
  />
)}
```

- [ ] **Step 5: Verify the full UI**

Run: `cd /home/nbrown/projects/ripken/.claude/worktrees/tidy-herding-dream && make dev`

1. Navigate to `http://localhost:3000/prospects`
2. Import the FanGraphs CSV
3. Verify FV badges appear in the table
4. Click a prospect row — verify the slide-out panel appears
5. Verify the panel shows: physical profile, signal factors, MiLB stats (or loading → result), scouting report, buzz, video link
6. Press Escape or click backdrop to close
7. Verify the panel slides in smoothly

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/prospects/page.tsx
git commit -m "feat: add prospect slide-out detail panel

Shows scouting report, MiLB stats from MLB Stats API, physical
profile, signal factor breakdown, buzz articles, and video link.
Panel slides in from right with backdrop and Escape to close."
```

---

### Task 8: Final Integration Test

- [ ] **Step 1: Full end-to-end test**

1. Start the app: `make dev`
2. Delete existing DB to start fresh: `rm data/fantasy_dashboard.db`
3. Restart the app (DB recreated on startup)
4. Import the FanGraphs CSV via the UI
5. Verify all prospects appear with FV badges, correct levels, and ranks
6. Click a prospect (e.g., Konnor Griffin)
7. Verify the detail panel shows:
   - Header: name, FV 70, SS · PIT · AAA · ETA 2026
   - Physical profile: Age, Height, Weight, B/T
   - Signal score with 6 factor bars
   - MiLB stats (fetched from MLB Stats API)
   - Full scouting report text
8. Re-import the same CSV
9. Verify prospects are updated (not duplicated) — check the API response says `updated: N`
10. Verify the app has no console errors

- [ ] **Step 2: Verify lint passes**

```bash
make lint
```

Expected: No lint errors.

- [ ] **Step 3: Final commit if any fixes needed**

Only commit if there were adjustments from the integration test. Otherwise, all code is already committed.
