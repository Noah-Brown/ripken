# Prospect Board Improvements — Design Spec

**Date:** 2026-03-28
**Status:** Approved

## Problem

The FanGraphs "The Board" CSV export has columns that don't match what the import code expects, causing Level and Rank to silently fail. Rich data (FV grade, scouting reports, physical profile, FanGraphs player IDs) is discarded. There's no way to click into a prospect for detail, and MiLB stats are not fetched automatically.

## Goals

1. Fix CSV import to correctly map all FanGraphs "The Board" columns
2. Store and display FV (Future Value) grades prominently
3. Add a slide-out detail panel with full scouting report, MiLB stats, physical profile, and buzz
4. Fetch real-time MiLB stats from the MLB Stats API

## Non-Goals

- Automated FanGraphs scraping (CSV is user-uploaded)
- Scouting grade extraction/parsing from report text
- Multi-source prospect ranking aggregation

---

## 1. CSV Column Mapping Fix

The FanGraphs "The Board" CSV has these columns:

```
Dynasty Rank, Re-Draft Rank, FYPD Eligible, Name, Org, Pos, FV,
Current Level, ETA, Trend, Age, Ht, Wt, B, T, Report, Video, PlayerId
```

Current import only looks for `Name`, `Player`, `Team`, `Org`, `Level`, `Rank`, `#`, `ETA`, `Position`, `Pos`. This causes:

- **`Current Level`** — not matched (code looks for `Level`)
- **`Dynasty Rank` / `Re-Draft Rank`** — not matched (code looks for `Rank` / `#`)
- **`FV`, `Report`, `Video`, `PlayerId`, `Age`, `Ht`, `Wt`, `Trend`** — discarded entirely

### Updated Column Mapping

| CSV Column | Target Field | Notes |
|---|---|---|
| `Name` | `player.full_name` | Already works |
| `Org` | `prospect.org` | Already works |
| `Pos` | `player.position` | Already works |
| `Current Level` | `prospect.level` | Add `"Current Level"` to lookup |
| `Dynasty Rank` | `prospect.fangraphs_rank` | Add `"Dynasty Rank"` to lookup |
| `Re-Draft Rank` | `prospect.redraft_rank` | New field |
| `ETA` | `prospect.eta` | Already works |
| `FV` | `prospect.fv` | New field |
| `Report` | `prospect.scouting_report` | New field |
| `Video` | `prospect.video_url` | New field |
| `Trend` | `prospect.trend` | New field |
| `Age` | `prospect.age` | New field (stored on prospect, not player, since it changes) |
| `Ht` | `prospect.height` | New field |
| `Wt` | `prospect.weight` | New field |
| `B` | `player.bats` | Already exists on Player model |
| `T` | `player.throws` | Already exists on Player model |
| `PlayerId` | `player.fangraphs_id_str` | See ID handling below |

### FanGraphs Player ID Handling

The CSV `PlayerId` values are strings like `"sa3065496"` (prospect IDs with an "sa" prefix). The current `player.fangraphs_id` column is `Integer`.

**Change:** Add a new `fangraphs_id_str` Text column to the Player model. Store the CSV `PlayerId` there during import. Keep the existing integer `fangraphs_id` column intact for the Chadwick crosswalk (which uses integer IDs). For MLB ID resolution, check `fangraphs_id` first (Chadwick match), then fall back to name-based search.

### Ignored Columns

- `FYPD Eligible` — not relevant to the dashboard, intentionally skipped.

### Re-import Behavior

When importing a CSV and a prospect already exists (matched by `player.full_name`), update the existing record rather than skipping. This allows re-importing an updated CSV to refresh ranks, FV, scouting reports, etc.

---

## 2. Database Schema Changes

### Prospect Model — New Columns

```python
class Prospect(Base):
    # ... existing columns ...
    fv = Column(Integer)                # FanGraphs Future Value (20-80 scale)
    scouting_report = Column(Text)      # Full scouting report text
    video_url = Column(Text)            # FanGraphs video link
    trend = Column(Text)               # Trending direction
    redraft_rank = Column(Integer)      # Re-draft ranking
    age = Column(Text)                  # Age at time of import
    height = Column(Text)              # e.g. "6' 4\""
    weight = Column(Text)              # e.g. "225"
    stats_fetched_at = Column(DateTime)  # When minor_league_stats was last refreshed
```

### Player Model — New Column

```python
fangraphs_id_str = Column(Text)  # FanGraphs prospect ID (e.g. "sa3065496")
```

The existing integer `fangraphs_id` column stays unchanged — it's used by the Chadwick crosswalk for MLB-level players. The new `fangraphs_id_str` column stores the string-format prospect IDs from the FanGraphs CSV.

No other Player model changes needed — `bats`, `throws` already exist.

### Migration

SQLite `create_all` automatically adds new columns to existing tables. No manual migration needed — new columns on Prospect and the new `fangraphs_id_str` on Player will be created on next startup.

---

## 3. MiLB Stats via MLB Stats API

### MLB Stats API Endpoint

```
GET https://statsapi.mlb.com/api/v1/people/{mlb_id}/stats?stats=season&group=hitting&season=2026&gameType=R&sportId=11,12,13,14,15,16
```

- `sportId` values: 11=AAA, 12=AA, 13=High-A, 14=A, 15=Short-A, 16=Rookie
- Separate calls for `group=hitting` and `group=pitching`

### Player ID Resolution

To call the MLB Stats API, we need `mlb_id`. Resolution strategy:

1. **Chadwick crosswalk:** If `player.fangraphs_id` matches a Chadwick entry, use the corresponding `mlb_id`
2. **MLB Stats API search:** `GET https://statsapi.mlb.com/api/v1/people/search?names={name}` — fallback for prospects not in Chadwick (very young prospects)
3. **Manual mapping:** If neither works, the prospect won't have MiLB stats until an ID is resolved

### New Backend Endpoint

```
GET /api/prospects/{prospect_id}/stats
```

Response:
```json
{
  "player_id": 123,
  "mlb_id": 456789,
  "season": 2026,
  "stats": [
    {
      "level": "AAA",
      "sport_id": 11,
      "hitting": {
        "avg": ".333",
        "ops": ".960",
        "hr": 12,
        "sb": 65,
        "k_pct": "22.1%",
        "bb_pct": "10.5%",
        "pa": 350,
        "games": 85
      },
      "pitching": null
    },
    {
      "level": "AA",
      "sport_id": 12,
      "hitting": {
        "avg": ".310",
        "ops": ".880",
        "hr": 8,
        "sb": 30,
        "k_pct": "20.5%",
        "bb_pct": "9.2%",
        "pa": 200,
        "games": 50
      },
      "pitching": null
    }
  ]
}
```

For pitchers, the `pitching` object replaces `hitting`:
```json
{
  "pitching": {
    "era": "2.45",
    "whip": "1.05",
    "k_per_9": "11.2",
    "bb_per_9": "2.8",
    "ip": "95.1",
    "games": 20
  }
}
```

### Caching

- Cache stats in `prospect.minor_league_stats` as JSON
- Add `prospect.stats_fetched_at` (DateTime) column
- Serve cached data if fetched within the last 6 hours
- Frontend calls the stats endpoint when the detail panel opens

---

## 4. Frontend — List View Changes

### New FV Column

Add an **FV** column between Rank and Signal in the prospect table:

- Displayed as an indigo pill badge: `FV 70`
- Color intensity scales with grade:
  - 70+ = deep indigo (elite)
  - 55-65 = medium indigo
  - 45-50 = light indigo
  - 40 or below = gray
- If no FV value, show "—"

### Clickable Rows

- Entire row is clickable (cursor pointer)
- Clicking opens the slide-out detail panel for that prospect
- Hover state on rows to indicate clickability

---

## 5. Frontend — Slide-out Detail Panel

A right-side drawer (approximately 55% viewport width) that slides in when a prospect row is clicked.

### Panel Sections (Top to Bottom)

**Header:**
- Close button (X) top-right
- Player name (large, bold)
- FV badge (indigo pill)
- Position, Org, Level, ETA in a subtitle line

**Physical Profile Bar:**
- Horizontal bar below the header
- Age | Height | Weight | Bats/Throws
- Compact, single line

**Signal Score:**
- Current signal badge (HOT/WARM/COLD with score)
- Factor breakdown displayed as small labeled bars or a compact grid:
  - Performance, Roster Need, Proximity, 40-Man, Service Time, Buzz

**MiLB Stats:**
- Section header: "MiLB Stats (2026 Season)"
- Stat cards in a grid layout
- For hitters: AVG, OPS, HR, SB, K%, BB%, PA, Games
- For pitchers: ERA, WHIP, K/9, BB/9, IP, Games
- If stats span multiple levels, show each level as a sub-row
- Loading state while fetching from API
- "No MLB ID mapped" message if we can't resolve the player

**Scouting Report:**
- Section header: "Scouting Report"
- Full FanGraphs report text
- Scrollable if long (max-height with overflow-y)
- Preserves paragraph breaks from the CSV

**Buzz:**
- Same buzz article display currently used in the expandable row, moved here
- Section header: "Recent Buzz"
- List of articles with title (linked), source, date, snippet

**Video Link:**
- If `video_url` is present, show a "Watch Video" link/button at the bottom

### Panel Behavior

- Slides in from the right with a CSS transition
- Semi-transparent backdrop overlay on the left (clicking it closes the panel)
- Body scroll is locked while panel is open
- Escape key closes the panel
- Panel is scrollable independently if content exceeds viewport height

---

## 6. Data Flow Summary

```
User uploads FanGraphs CSV
  → POST /api/prospects/import
    → Parse all 18 columns
    → Create/update Player records (name, position, bats, throws, fangraphs_id)
    → Create/update Prospect records (all new fields)
    → Attempt MLB ID resolution via Chadwick crosswalk
    → Return {imported, updated, skipped}

User clicks prospect row
  → Frontend opens slide-out panel
  → Panel renders immediately with cached data (scouting report, FV, profile)
  → Panel calls GET /api/prospects/{id}/stats
    → Backend checks cache (< 6 hours old → return cached)
    → Otherwise fetches from MLB Stats API using mlb_id
    → Caches result in minor_league_stats JSON + stats_fetched_at
    → Returns stats response
  → Panel renders MiLB stats when response arrives
```

---

## 7. Files to Create/Modify

### Backend
- `backend/database/models.py` — Add columns to Prospect, add fangraphs_id_str to Player
- `backend/api/routes/prospects.py` — Fix CSV import mapping, add stats endpoint, update GET response
- `backend/analytics/prospect_signals.py` — Include new fields in signal response
- `backend/ingestion/player_id_crosswalk.py` — Handle fangraphs_id as Text
- New: `backend/ingestion/mlb_stats_api.py` — MiLB stats fetcher

### Frontend
- `frontend/src/app/prospects/page.tsx` — Add FV column, clickable rows, slide-out panel component
- `frontend/src/lib/api.ts` — Add prospect stats fetch function (if not already generic)
