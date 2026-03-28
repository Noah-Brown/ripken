# MLB Lineup Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch batting lineups from the MLB Stats API game feed for today's scheduled/live games and populate the existing `lineups` table on a 10-minute interval.

**Architecture:** New `fetch_lineups` function in `backend/ingestion/mlb_stats.py` queries the `games` table for today's non-final games, fetches each game's live feed, extracts `battingOrder` from the boxscore, resolves MLB IDs to internal player IDs (creating minimal records as needed), upserts lineup rows, and deletes stale entries (late scratches). A scheduler job runs this every 10 minutes, and it also runs at startup.

**Tech Stack:** Python, FastAPI, SQLAlchemy (async), httpx, APScheduler, SQLite

---

### Task 1: Add `fetch_lineups` function to `mlb_stats.py`

**Files:**
- Modify: `backend/ingestion/mlb_stats.py`

- [ ] **Step 1: Add Lineup import**

At the top of `backend/ingestion/mlb_stats.py`, add `Lineup` to the existing model imports:

```python
from backend.database.models import (
    Game,
    Lineup,
    PitcherAppearance,
    Player,
    ProbablePitcher,
    Transaction,
)
```

- [ ] **Step 2: Add `fetch_game_lineups` function**

Add this function after the `fetch_schedule` section (after line 123), before the rosters section. This fetches lineup data for a single game from the live feed:

```python
# ---------------------------------------------------------------------------
# 1b. Game Lineups
# ---------------------------------------------------------------------------


async def fetch_game_lineups(db: AsyncSession, game_id: int) -> int:
    """Fetch lineup data for a single game from the live feed and upsert into lineups table.

    Returns the number of lineup entries upserted.
    """
    feed_url = f"https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live"
    async with httpx.AsyncClient() as client:
        resp = await client.get(feed_url, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()

    game_data = data.get("gameData", {})
    teams_info = game_data.get("teams", {})

    boxscore = data.get("liveData", {}).get("boxscore", {})
    teams_box = boxscore.get("teams", {})

    count = 0
    for side in ("away", "home"):
        team_box = teams_box.get(side, {})
        batting_order = team_box.get("battingOrder", [])
        if not batting_order:
            continue

        team_abbr = teams_info.get(side, {}).get("abbreviation", "")
        if not team_abbr:
            continue

        players_data = team_box.get("players", {})

        # Track player_ids we upsert so we can delete stale entries
        upserted_player_ids = []

        for order_idx, mlb_id in enumerate(batting_order, start=1):
            player_key = f"ID{mlb_id}"
            player_info = players_data.get(player_key, {})
            person = player_info.get("person", {})

            # Resolve mlb_id -> internal player_id
            result = await db.execute(
                select(Player.id).where(Player.mlb_id == mlb_id)
            )
            player_id = result.scalar_one_or_none()

            if player_id is None:
                ins = sqlite_insert(Player).values(
                    mlb_id=mlb_id,
                    full_name=person.get("fullName", f"Unknown ({mlb_id})"),
                    team=team_abbr,
                    position=player_info.get("position", {}).get("abbreviation", ""),
                    status="active",
                )
                ins = ins.on_conflict_do_nothing(index_elements=["mlb_id"])
                await db.execute(ins)
                await db.flush()
                result = await db.execute(
                    select(Player.id).where(Player.mlb_id == mlb_id)
                )
                player_id = result.scalar_one_or_none()

            if player_id is None:
                continue

            upserted_player_ids.append(player_id)

            stmt = sqlite_insert(Lineup).values(
                game_id=game_id,
                team=team_abbr,
                player_id=player_id,
                batting_order=order_idx,
                is_confirmed=1,
                source="mlb",
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["game_id", "team", "player_id"],
                set_={
                    "batting_order": stmt.excluded.batting_order,
                    "is_confirmed": stmt.excluded.is_confirmed,
                },
            )
            await db.execute(stmt)
            count += 1

        # Delete stale lineup entries for this game/team (late scratches)
        if upserted_player_ids:
            from sqlalchemy import delete

            await db.execute(
                delete(Lineup).where(
                    Lineup.game_id == game_id,
                    Lineup.team == team_abbr,
                    Lineup.player_id.notin_(upserted_player_ids),
                )
            )

    return count
```

- [ ] **Step 3: Add `fetch_lineups` orchestrator function**

Add this function right after `fetch_game_lineups`:

```python
async def fetch_lineups(db: AsyncSession) -> None:
    """Fetch lineups for all of today's scheduled or live games."""
    today = date.today().isoformat()

    result = await db.execute(
        select(Game.id).where(
            Game.date == today,
            Game.status.in_(["scheduled", "live"]),
        )
    )
    game_ids = [row[0] for row in result.all()]

    if not game_ids:
        logger.info("No scheduled/live games today for lineup fetch")
        return

    logger.info("Fetching lineups for %d games", len(game_ids))
    total = 0
    for game_id in game_ids:
        try:
            count = await fetch_game_lineups(db, game_id)
            total += count
        except httpx.HTTPStatusError as exc:
            logger.warning("Failed to fetch lineup for game %d: %s", game_id, exc)
        except Exception:
            logger.exception("Failed to fetch lineup for game %d", game_id)

    await db.commit()
    logger.info("Upserted %d total lineup entries across %d games", total, len(game_ids))
```

- [ ] **Step 4: Add `lineups` to CLI choices**

In the `main()` function at the bottom of `mlb_stats.py`, update the `choices` list and add the handler:

Update the `choices` argument:
```python
choices=["schedule", "rosters", "probable_pitchers", "transactions", "game_results", "lineups"],
```

Add the handler in the `if/elif` chain (before the final `elif args.action == "game_results"`):
```python
        elif args.action == "lineups":
            await fetch_lineups(db)
```

- [ ] **Step 5: Verify syntax**

Run: `cd /home/nbrown/projects/ripken/.claude/worktrees/indexed-singing-creek && python -c "from backend.ingestion.mlb_stats import fetch_lineups, fetch_game_lineups; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/ingestion/mlb_stats.py
git commit -m "feat: add lineup ingestion from MLB Stats API game feed"
```

---

### Task 2: Wire up scheduler job and startup

**Files:**
- Modify: `backend/ingestion/scheduler.py`

- [ ] **Step 1: Add `job_sync_lineups` function**

Add this function after `job_sync_schedule` (after line 42) in `scheduler.py`:

```python
async def job_sync_lineups():
    from backend.ingestion.mlb_stats import fetch_lineups

    await _run_job("sync_lineups", fetch_lineups)
```

- [ ] **Step 2: Add scheduler job in `create_scheduler`**

Add the lineup job in the `create_scheduler` function, right after the schedule job (after line 133). Use the config setting for the interval:

```python
    # Game lineups — every 10 minutes
    scheduler.add_job(
        job_sync_lineups, "interval",
        minutes=settings.lineup_check_interval_minutes,
        id="sync_lineups",
    )
```

- [ ] **Step 3: Add lineup sync to startup jobs**

In `run_startup_jobs`, add the lineup sync after `job_sync_schedule` (since lineups depend on games existing in the DB):

```python
async def run_startup_jobs():
    """Run critical jobs on startup so the dashboard isn't empty."""
    logger.info("Running startup data sync...")
    await job_sync_schedule()
    await job_sync_lineups()
    await job_sync_probable_pitchers()
    await job_sync_rosters()
    await job_sync_yahoo_rosters()
    logger.info("Startup sync complete.")
```

- [ ] **Step 4: Verify syntax**

Run: `cd /home/nbrown/projects/ripken/.claude/worktrees/indexed-singing-creek && python -c "from backend.ingestion.scheduler import job_sync_lineups, create_scheduler; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/ingestion/scheduler.py
git commit -m "feat: add lineup sync scheduler job (10min interval + startup)"
```

---

### Task 3: Test with a real game

**Files:** None (manual verification)

- [ ] **Step 1: Run the ingestion manually**

Run the CLI to verify it works against real MLB data:

```bash
cd /home/nbrown/projects/ripken/.claude/worktrees/indexed-singing-creek
python -m backend.ingestion.mlb_stats --action schedule --start-date 2026-03-28 --end-date 2026-03-28
python -m backend.ingestion.mlb_stats --action lineups
```

Expected: Log output showing games found and lineup entries upserted (count depends on how many games have posted lineups).

- [ ] **Step 2: Verify data in the database**

```bash
cd /home/nbrown/projects/ripken/.claude/worktrees/indexed-singing-creek
sqlite3 data/fantasy_dashboard.db "SELECT g.home_team, g.away_team, COUNT(l.id) as lineup_count FROM games g LEFT JOIN lineups l ON g.id = l.game_id WHERE g.date = '2026-03-28' GROUP BY g.id ORDER BY g.game_time;"
```

Expected: Games with lineup counts > 0 for games that have posted lineups, 0 for games that haven't yet.

- [ ] **Step 3: Verify lineup details**

```bash
sqlite3 data/fantasy_dashboard.db "SELECT l.batting_order, p.full_name, l.team, l.is_confirmed FROM lineups l JOIN players p ON l.player_id = p.id JOIN games g ON l.game_id = g.id WHERE g.date = '2026-03-28' ORDER BY l.game_id, l.team, l.batting_order LIMIT 20;"
```

Expected: Batting order 1-9 with player names, team abbreviations, and `is_confirmed = 1`.

- [ ] **Step 4: Commit (if any fixes were needed)**

Only if changes were made during testing:
```bash
git add backend/ingestion/mlb_stats.py
git commit -m "fix: lineup ingestion adjustments from live testing"
```
