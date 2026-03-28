# Waivers Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the waivers page with a position-grouped view showing owned + available players with FanGraphs ROS projections, sourced from manually updated CSVs.

**Architecture:** Projection CSVs stored in `data/projections/`, ingested via CLI into `player_stats` table. New waivers API endpoint joins projections with league ownership data. Frontend shows position-grouped tables with batter/pitcher-specific stat columns.

**Tech Stack:** Python/FastAPI, SQLAlchemy, pandas (CSV ingestion), Next.js/React/Tailwind.

**Spec:** `docs/superpowers/specs/2026-03-28-waivers-page-redesign-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `data/projections/batting.csv` | Create | FanGraphs ROS batting projections |
| `data/projections/pitching.csv` | Create | FanGraphs ROS pitching projections |
| `backend/ingestion/fangraphs.py` | Modify | Add `projections-csv` CLI action |
| `backend/api/routes/waivers.py` | Modify | Replace endpoint with position-grouped projections |
| `frontend/src/app/waivers/page.tsx` | Modify | Full rewrite with new layout |

---

### Task 1: Add projection CSVs and ingestion CLI

**Files:**
- Create: `data/projections/batting.csv`
- Create: `data/projections/pitching.csv`
- Modify: `backend/ingestion/fangraphs.py`

- [ ] **Step 1: Copy CSV files into repo**

```bash
mkdir -p data/projections
cp '/mnt/c/Users/noahb/Downloads/fangraphs-leaderboard-projections (8).csv' data/projections/batting.csv
cp '/mnt/c/Users/noahb/Downloads/fangraphs-leaderboard-projections (7).csv' data/projections/pitching.csv
```

- [ ] **Step 2: Add `sync_projections_from_csv()` function**

Add to `backend/ingestion/fangraphs.py` before the `if __name__` block:

```python
async def sync_projections_from_csv(db: AsyncSession) -> None:
    """Load ROS projections from local CSV files in data/projections/."""
    import os

    today = date.today().isoformat()
    base_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "projections")
    base_dir = os.path.normpath(base_dir)

    # Build both ID maps for matching
    fg_id_map = await _build_fg_id_map(db)

    # Also build mlb_id map for MLBAMID matching
    result = await db.execute(
        select(Player.id, Player.mlb_id).where(Player.mlb_id.isnot(None))
    )
    mlb_id_map = {row.mlb_id: row.id for row in result.all()}

    for csv_name, stat_type in [
        ("batting.csv", "projections_batting"),
        ("pitching.csv", "projections_pitching"),
    ]:
        path = os.path.join(base_dir, csv_name)
        if not os.path.exists(path):
            print(f"  Skipping {csv_name} — file not found at {path}")
            continue

        df = pd.read_csv(path)
        print(f"  Loaded {len(df)} rows from {csv_name}")

        # Try MLBAMID first, then PlayerId (FanGraphs ID)
        count = 0
        for _, row in df.iterrows():
            player_id = None

            # Try MLBAMID -> mlb_id
            mlbam = row.get("MLBAMID")
            if pd.notna(mlbam):
                player_id = mlb_id_map.get(int(mlbam))

            # Fallback: PlayerId -> fangraphs_id
            if player_id is None:
                fg_id = row.get("playerid") or row.get("PlayerId")
                if pd.notna(fg_id):
                    try:
                        player_id = fg_id_map.get(int(fg_id))
                    except (ValueError, TypeError):
                        pass

            if player_id is None:
                continue

            stats_dict = {
                k: (None if pd.isna(v) else v)
                for k, v in row.to_dict().items()
                if k not in ("playerid", "PlayerId", "MLBAMID")
            }

            stmt = sqlite_insert(PlayerStats).values(
                player_id=player_id,
                date=today,
                source="fangraphs",
                stat_type=stat_type,
                stats=json.dumps(stats_dict),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["player_id", "date", "source", "stat_type"],
                set_={"stats": stmt.excluded.stats},
            )
            await db.execute(stmt)
            count += 1

        await db.commit()
        print(f"  Stored {count} {stat_type} projection rows")

    print("CSV projections import complete.")
```

- [ ] **Step 3: Add `projections-csv` CLI action**

Update the `__main__` block in `fangraphs.py`:

```python
    parser.add_argument(
        "--action",
        choices=["stats", "projections", "projections-csv"],
        default="stats",
        help="Which data to fetch",
    )
```

Add to the main() if/elif chain:

```python
            elif args.action == "projections-csv":
                await sync_projections_from_csv(db)
```

- [ ] **Step 4: Lint and verify**

Run: `ruff check backend/ingestion/fangraphs.py`

- [ ] **Step 5: Commit**

```bash
git add data/projections/ backend/ingestion/fangraphs.py
git commit -m "feat: add CSV-based projection import from FanGraphs"
```

---

### Task 2: Rewrite waivers API endpoint

**Files:**
- Modify: `backend/api/routes/waivers.py`

- [ ] **Step 1: Replace the endpoint**

Full rewrite of `backend/api/routes/waivers.py`:

```python
"""Waiver wire API routes — position-grouped with projections."""

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.database.models import (
    LeagueRoster,
    LeagueTeam,
    Player,
    PlayerStats,
    UserLeague,
)

router = APIRouter(prefix="/api", tags=["waivers"])

PITCHER_POSITIONS = {"SP", "RP", "P"}

BATTER_KEYS = ["PA", "R", "HR", "RBI", "SB", "AVG", "OBP", "SLG", "OPS", "wRC+", "Off"]
PITCHER_KEYS = ["IP", "W", "QS", "SV", "ERA", "WHIP", "K/9", "SO", "WAR"]

POSITION_ORDER = [
    "C", "1B", "2B", "SS", "3B", "OF", "Util", "DH",
    "CI", "MI", "SP", "RP", "P", "BN", "IL", "IL+", "NA",
]


def _extract_projection(stats_json: str | None, keys: list[str]) -> dict | None:
    """Parse a stats JSON blob and extract only the requested keys."""
    if not stats_json:
        return None
    try:
        raw = json.loads(stats_json)
    except (json.JSONDecodeError, TypeError):
        return None
    proj = {}
    for k in keys:
        v = raw.get(k)
        if v is not None:
            proj[k] = v
    return proj if proj else None


def _sort_key(player: dict, is_pitcher: bool) -> float:
    """Sort key: Off desc for batters, WAR desc for pitchers."""
    proj = player.get("projection") or {}
    if is_pitcher:
        return -(proj.get("WAR") or 0)
    return -(proj.get("Off") or 0)


@router.get("/waivers/{league_id}")
async def get_waivers(
    league_id: int,
    position: str | None = Query(None, description="Filter by position"),
    db: AsyncSession = Depends(get_db_session),
):
    """All players with projections, grouped by position, with ownership."""
    # Verify league
    league_result = await db.execute(
        select(UserLeague).where(UserLeague.id == league_id)
    )
    league = league_result.scalar_one_or_none()
    if not league:
        return {"league_id": league_id, "error": "League not found", "positions": {}}

    # User's team keys
    team_result = await db.execute(
        select(LeagueTeam.yahoo_team_key).where(
            LeagueTeam.league_id == league_id,
            LeagueTeam.is_current_user == 1,
        )
    )
    user_team_keys = {row[0] for row in team_result.all()}

    # Ownership map: player_id -> {team_name, is_mine, roster_position}
    ownership_result = await db.execute(
        select(
            LeagueRoster.player_id,
            LeagueRoster.yahoo_team_name,
            LeagueRoster.yahoo_team_key,
            LeagueRoster.roster_position,
        ).where(
            LeagueRoster.league_id == league_id,
            LeagueRoster.player_id.isnot(None),
        )
    )
    ownership_map: dict[int, dict] = {}
    for row in ownership_result.all():
        if row.player_id is not None:
            ownership_map[row.player_id] = {
                "team_name": row.yahoo_team_name,
                "is_mine": row.yahoo_team_key in user_team_keys,
                "roster_position": row.roster_position,
            }

    # Load all projections (most recent date per player)
    # Batting projections
    batting_proj: dict[int, str] = {}
    batting_result = await db.execute(
        select(PlayerStats.player_id, PlayerStats.stats)
        .where(
            PlayerStats.source == "fangraphs",
            PlayerStats.stat_type == "projections_batting",
        )
        .order_by(PlayerStats.date.desc())
    )
    for row in batting_result.all():
        if row.player_id not in batting_proj:
            batting_proj[row.player_id] = row.stats

    # Pitching projections
    pitching_proj: dict[int, str] = {}
    pitching_result = await db.execute(
        select(PlayerStats.player_id, PlayerStats.stats)
        .where(
            PlayerStats.source == "fangraphs",
            PlayerStats.stat_type == "projections_pitching",
        )
        .order_by(PlayerStats.date.desc())
    )
    for row in pitching_result.all():
        if row.player_id not in pitching_proj:
            pitching_proj[row.player_id] = row.stats

    # All player IDs with projections
    all_proj_ids = set(batting_proj.keys()) | set(pitching_proj.keys())

    # Load player info for all projected players
    player_result = await db.execute(
        select(Player).where(Player.id.in_(all_proj_ids))
    )
    players_by_id = {p.id: p for p in player_result.scalars().all()}

    # Build position groups
    positions: dict[str, list] = {}

    for pid in all_proj_ids:
        player = players_by_id.get(pid)
        if not player:
            continue

        ownership = ownership_map.get(pid)
        is_pitcher = player.position in PITCHER_POSITIONS if player.position else False

        # Determine position for grouping
        if ownership:
            pos = ownership["roster_position"] or player.position or "BN"
        else:
            pos = player.position or "Util"

        # Filter by position if requested
        if position and pos != position:
            # Also check if player's natural position matches
            if player.position != position:
                continue

        # Get projection
        if is_pitcher:
            proj = _extract_projection(pitching_proj.get(pid), PITCHER_KEYS)
        else:
            proj = _extract_projection(batting_proj.get(pid), BATTER_KEYS)

        entry = {
            "player_id": pid,
            "full_name": player.full_name,
            "team": player.team,
            "status": player.status or "active",
            "owner": ownership["team_name"] if ownership else None,
            "is_mine": ownership["is_mine"] if ownership else False,
            "is_available": ownership is None,
            "projection": proj,
        }

        if pos not in positions:
            positions[pos] = []
        positions[pos].append(entry)

    # Sort within each position group
    for pos, players in positions.items():
        is_pitcher_pos = pos in PITCHER_POSITIONS
        players.sort(key=lambda p: _sort_key(p, is_pitcher_pos))

    # Order position groups
    ordered: dict[str, list] = {}
    for pos in POSITION_ORDER:
        if pos in positions:
            ordered[pos] = positions[pos]
    for pos in positions:
        if pos not in ordered:
            ordered[pos] = positions[pos]

    return {
        "league_id": league_id,
        "league_name": league.league_name,
        "positions": ordered,
    }
```

- [ ] **Step 2: Lint**

Run: `ruff check backend/api/routes/waivers.py`

- [ ] **Step 3: Commit**

```bash
git add backend/api/routes/waivers.py
git commit -m "feat: replace waivers API with position-grouped projections"
```

---

### Task 3: Rewrite waivers frontend page

**Files:**
- Modify: `frontend/src/app/waivers/page.tsx`

- [ ] **Step 1: Full rewrite**

Replace `frontend/src/app/waivers/page.tsx` with a new page that:

- Fetches leagues from `/api/leagues`, auto-selects first
- Fetches `/api/waivers/{league_id}` when league selected
- Renders position sections vertically
- Shows batter columns (PA, R, HR, RBI, SB, AVG, OBP, SLG, OPS, wRC+, Off) for batter positions
- Shows pitcher columns (IP, W, QS, SV, ERA, WHIP, K/9, SO, WAR) for pitcher positions
- Green player names for your players, "FA" in green for available players
- Position filter dropdown
- League selector dropdown

Key implementation details:
- Pitcher positions are `SP`, `RP`, `P` — everything else uses batter columns
- Rate stats formatted: AVG/OBP/SLG to 3 decimals, ERA/WHIP/K9/OPS to 2 decimals
- Count stats as integers (PA, R, HR, RBI, SB, W, QS, SV, SO)
- Off and WAR to 1 decimal
- wRC+ to integer
- IP to 1 decimal

- [ ] **Step 2: Build and verify**

Run: `cd frontend && npx next build`
Expected: Build succeeds, `/waivers` page compiles.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/waivers/page.tsx
git commit -m "feat: redesign waivers page with position-grouped projections"
```

---

### Task 4: Deploy, ingest projections, and verify

**Files:** None (deployment + data loading)

- [ ] **Step 1: Push**

```bash
git push
```

- [ ] **Step 2: Deploy**

```bash
ssh ripken 'cd ~/ripken && git pull && docker compose up -d --build backend frontend'
```

- [ ] **Step 3: Ingest projections on production**

Wait for deploy to complete, then stop backend to avoid DB lock and run ingestion:

```bash
ssh ripken 'cd ~/ripken && docker compose stop backend && \
  docker compose run --rm -T backend .venv/bin/python -m backend.ingestion.fangraphs --action projections-csv && \
  docker compose start backend'
```

Expected output: counts of stored batting and pitching projection rows.

- [ ] **Step 4: Verify production**

- Open `https://ripken.noahbrown.io/waivers` — should show league selector, position groups with projections
- Check that owned players show owner names, available show "FA"
- Verify sort order: batters by Off desc, pitchers by WAR desc
- Check stat formatting looks correct
