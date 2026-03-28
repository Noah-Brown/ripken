# League-Wide Roster Tracking & Ownership

**Date:** 2026-03-28
**Goal:** Track all teams' rosters across Yahoo leagues. Show player ownership on the bullpen page with a league selector. Add a new league page showing all rostered players grouped by position.

## Data Model

### New table: `league_teams`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto |
| league_id | FK -> user_leagues.id | |
| yahoo_team_key | Text, unique | e.g., "mlb.l.12345.t.3" |
| team_name | Text | e.g., "Noah's Sluggers" |
| manager_name | Text, nullable | |
| is_current_user | Integer | 0 or 1 |

### New table: `league_rosters`

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | Auto |
| league_id | FK -> user_leagues.id | |
| yahoo_team_key | Text | FK-like ref to league_teams |
| yahoo_team_name | Text | Denormalized for fast lookups |
| player_id | FK -> players.id, nullable | Null if unmatched |
| yahoo_player_key | Text | |
| yahoo_player_name | Text | |
| roster_position | Text | e.g., "C", "SP", "RP", "BN" |

Unique constraint: `(league_id, yahoo_team_key, yahoo_player_key)`

## Yahoo API & Sync

### New client method: `get_league_teams(db, league_key)`

Calls `/league/{league_key}/teams`. Returns all teams (not just user's). Already partially implemented in `get_team_key()` which hits the same endpoint.

Returns: `list[{team_key, team_name, manager_name, is_current_user}]`

### New sync job: `sync_league_rosters(db)`

- Runs every **1 hour** (separate from the 15-min user roster sync)
- Does NOT run at startup (too slow — ~15 API calls per league)
- For each league:
  1. Call `get_league_teams()` → upsert into `league_teams`
  2. For each team, call `get_roster()` → full replace into `league_rosters`
  3. Uses `map_roster_players()` for player ID matching
  4. 1-second delay between teams for rate limiting

### Existing sync unchanged

`sync_all_rosters()` continues to run every 15 min, syncing only the user's roster to `user_rosters`.

## API Changes

### `GET /api/leagues`

New endpoint. Returns the user's leagues for dropdown population.

```json
[
  {"id": 1, "league_name": "My H2H League", "yahoo_league_key": "mlb.l.12345"},
  {"id": 2, "league_name": "My Roto League", "yahoo_league_key": "mlb.l.67890"}
]
```

### `GET /api/bullpen` — Add `league_id` param

When `league_id` is provided:
- Query `league_rosters` for that league to build ownership map
- Each reliever gets an `ownership` field:
  - `null` — free agent
  - `{"team_name": "...", "is_mine": true}` — on your roster
  - `{"team_name": "...", "is_mine": false}` — taken by someone else
- `is_rostered` remains true/false (true if owned by you in ANY league) for backwards compat

When `league_id` is omitted, behavior unchanged.

### `GET /api/league/{league_id}/rosters`

New endpoint. Returns all rostered players grouped by position.

```json
{
  "league_name": "My League",
  "teams": [
    {"yahoo_team_key": "...", "team_name": "Noah's Sluggers", "is_current_user": true}
  ],
  "positions": {
    "C": [
      {"player_name": "...", "team": "NYY", "owner": "Noah's Sluggers", "is_current_user": true, "player_id": 123}
    ],
    "SP": [],
    "RP": []
  }
}
```

Position order: C, 1B, 2B, SS, 3B, OF, Util, SP, RP, BN, DL

## Frontend: Bullpen Page Changes

- **League selector dropdown** in filter bar, populated from `GET /api/leagues`
- Selecting a league passes `league_id` to the bullpen API
- **Roster indicators** (three states):
  - Green dot — yours (hover: "On your roster")
  - Orange dot — taken (hover: shows owner team name)
  - No dot — free agent
- "My Relievers" filter still works (filters to `ownership.is_mine`)

## Frontend: New League Page (`/league`)

- **League selector dropdown** at top
- **Position sections** listed vertically: C, 1B, 2B, SS, 3B, OF, Util, SP, RP, BN, DL
- Each section is a table: Player | MLB Team | Owner
- Your players highlighted in green
- Sortable by player name or owner within each position group

## What's NOT Changing

- `user_rosters` table and its sync (15-min interval)
- Existing roster page (`/roster`)
- Yahoo OAuth flow
- Reliever role classification
