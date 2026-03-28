# Bullpen Page Redesign

**Date:** 2026-03-28
**Goal:** Rework the bullpen dashboard to match the FanGraphs Roster Resource closer depth chart layout, using data we already ingest.

## API Changes

### Endpoint: `GET /api/bullpen`

Response adds:
- `day_columns`: array of 7 date strings (most recent first) at top level
- Per reliever:
  - `season_g`, `season_ip`, `season_era`, `season_sv`, `season_hld`, `season_k9`, `season_k_pct` — computed from `pitcher_appearances` where `is_starter = 0`
  - `daily_pitches`: array of 7 values aligned with `day_columns` — pitch count (int) or null for rest days

Removed fields: `usage_heatmap`, `evidence`, `appearances_last_7d`, `avg_leverage_last_14d`, `saves_last_14d`, `holds_last_14d`.

### Season Stats Computation

Single aggregate query on `pitcher_appearances` where `is_starter = 0`, grouped by `player_id`:
- G: `COUNT(*)`
- IP: `SUM(innings_pitched)`
- ERA: `SUM(earned_runs) / SUM(innings_pitched) * 9` (0.00 if zero IP)
- SV: `SUM(save)`
- HLD: `SUM(hold)`
- K/9: `SUM(strikeouts) / SUM(innings_pitched) * 9` (0.0 if zero IP)
- K%: `SUM(strikeouts) / (SUM(strikeouts) + SUM(walks) + SUM(hits_allowed))` (0.0 if zero denominator)

### Daily Pitches

Query `pitcher_appearances` for the last 7 days. Pivot into a date-aligned array matching `day_columns`. Null for days with no appearance.

## Frontend Changes

### File: `frontend/src/app/bullpen/page.tsx`

### Two Views (toggle button)

**Team-Grouped View (default):**
- Teams listed alphabetically, each as a section with a header row
- Within each team, relievers ordered: closer > setup > middle > long > mop_up
- Rostered players get a green name highlight

**Flat Table View:**
- Single table across all teams
- Sortable by column header click
- Default sort: role hierarchy, then team

### Table Columns

| Pitcher | THR | Role | G | IP | ERA | SV | HLD | K/9 | K% | Day7 | Day6 | Day5 | Day4 | Day3 | Day2 | Day1 |

- **Pitcher**: Name with green highlight if rostered, team shown below name in team-grouped view or as a separate indicator in flat view
- **THR**: R or L
- **Role**: Color-coded badge (closer=red, setup=amber, middle=blue, long/mop_up=zinc)
- **Season stats**: Monospace numbers
- **Daily columns**: Pitch count if pitched, dash/empty if rest. Red background tint if >25 pitches.

### Filters
- Role dropdown
- Team dropdown
- "My Relievers" toggle
- View toggle: "By Team" / "All Players"

## What's NOT Changing
- Database models (no new tables or columns)
- Reliever role classification algorithm
- Scheduler / ingestion pipeline
- Availability estimation logic
