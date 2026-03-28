# Waivers Page Redesign — Position-Grouped with Projections

**Date:** 2026-03-28
**Goal:** Replace the waivers page with a position-grouped view showing all players (owned + available) with FanGraphs ROS projections. Include a CLI-based CSV projection import.

## Projection Data Pipeline

### Storage

CSVs committed to repo:
- `data/projections/batting.csv` — FanGraphs Depth Charts ROS batting projections
- `data/projections/pitching.csv` — FanGraphs Depth Charts ROS pitching projections

### Ingestion CLI

```bash
python -m backend.ingestion.fangraphs --action projections-csv
```

Reads both CSVs from `data/projections/`, maps players via `MLBAMID` → `Player.mlb_id` (fallback: `PlayerId` → `Player.fangraphs_id`), upserts into `player_stats` with `source="fangraphs"`, `stat_type="projections_batting"` / `"projections_pitching"`. Stores the full row as a JSON blob.

### Update Workflow

1. Download fresh CSVs from FanGraphs
2. Replace files in `data/projections/`
3. Commit, push, deploy
4. Run CLI on server: `docker compose exec backend .venv/bin/python -m backend.ingestion.fangraphs --action projections-csv`

## API Changes

### Replace `GET /api/waivers/{league_id}`

**Query params:** `position` (optional filter)

**Response:**
```json
{
  "league_id": 1,
  "league_name": "My League",
  "positions": {
    "C": [
      {
        "player_id": 123,
        "full_name": "Cal Raleigh",
        "team": "SEA",
        "status": "active",
        "owner": "Noah's Sluggers",
        "is_mine": true,
        "is_available": false,
        "projection": {
          "PA": 630, "R": 87, "HR": 39, "RBI": 100, "SB": 7,
          "AVG": 0.229, "OBP": 0.328, "SLG": 0.486, "OPS": 0.814,
          "wRC+": 128.3, "Off": 19.3
        }
      }
    ],
    "SP": [
      {
        "player_id": 789,
        "full_name": "Tarik Skubal",
        "team": "DET",
        "status": "active",
        "owner": null,
        "is_mine": false,
        "is_available": true,
        "projection": {
          "IP": 197, "W": 14, "QS": 22, "SV": 0,
          "ERA": 2.69, "WHIP": 0.985, "K/9": 11.02, "SO": 242, "WAR": 6.31
        }
      }
    ]
  }
}
```

### Data Sources

- **Owned players:** From `league_rosters` table (league-wide ownership)
- **Available players:** All players in `player_stats` with projections that are NOT in `league_rosters` for the given league
- **Projections:** From `player_stats` where `source="fangraphs"` and `stat_type` in `("projections_batting", "projections_pitching")`
- **Position grouping:** Yahoo roster position if owned, `Player.position` if available
- **Ownership:** From `league_rosters` + `league_teams` (same as bullpen page)

### Sort Order

- Batter positions: sorted by `Off` descending
- Pitcher positions: sorted by `WAR` descending

### Position Types

Pitcher positions: SP, RP, P
Batter positions: everything else (C, 1B, 2B, SS, 3B, OF, Util, CI, MI, DH, BN, IL, etc.)

BN and IL players are grouped as their own position sections. Players on the bench show with batter or pitcher columns based on their natural position.

## Frontend: Waivers Page Replacement

### File: `frontend/src/app/waivers/page.tsx` (full rewrite)

### Layout

- League selector dropdown at top
- Position filter dropdown (optional, "All Positions" default)
- Position sections listed vertically

### Table Columns

**Batter positions:**
| Player | Owner | PA | R | HR | RBI | SB | AVG | OBP | SLG | OPS | wRC+ | Off |

**Pitcher positions:**
| Player | Owner | IP | W | QS | SV | ERA | WHIP | K/9 | SO | WAR |

### Row Styling

- Green name text = your player
- Owner column: team name if owned, "FA" in green if available
- Stats in monospace, rate stats formatted to 3 decimals (AVG, OBP, SLG) or 2 decimals (ERA, WHIP, K/9, OPS)

## What's NOT Changing

- `/league` page (stays as-is)
- `league_rosters` / `league_teams` tables and sync
- Waiver scoring algorithm code (stays in codebase, just not called by new endpoint)
- Bullpen page ownership features
