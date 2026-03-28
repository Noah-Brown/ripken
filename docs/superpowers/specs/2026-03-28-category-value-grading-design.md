# Category Value Grading System

## Overview

A value engine that grades players based on how much they help your specific fantasy team, driven by category-level need analysis. Includes a dedicated Team Analysis page and enhanced waivers page with value scores. Designed to support both H2H and roto league formats, with future reuse for trade assessment.

## Requirements

- Two leagues: H2H weekly (2025 Fantasy Baseball) and year-long roto (BUSH2026)
- Value is relative to team needs, not absolute player quality
- Single composite score (0-100) with per-category breakdown on demand
- Team Analysis dedicated page with radar chart visualization
- Condensed needs panel on waivers page for context while browsing
- Data source: FanGraphs rest-of-season projections (already imported)
- Waiver value based on rest-of-season needs only (no weekly matchup influence)
- Future-proof for trade assessment (fairness + team-need impact)

## Stat Mapping

### Yahoo Scoring Categories

`UserLeague.scoring_categories` stores the raw Yahoo API `stat_categories` dict as JSON (via `json.dumps()` in `yahoo/sync.py`). This is a nested structure from Yahoo's settings API, not a flat list of stat names. The value engine must parse this to extract canonical stat abbreviations.

Example of the Yahoo `stat_categories` structure (abbreviated):
```json
{
  "stats": [
    {"stat": {"stat_id": 60, "enabled": "1", "name": "Hits/At Bats", "display_name": "H/AB", "sort_order": "1", "position_type": "B"}},
    {"stat": {"stat_id": 7, "enabled": "1", "name": "Runs", "display_name": "R", "sort_order": "1", "position_type": "B"}},
    {"stat": {"stat_id": 12, "enabled": "1", "name": "Home Runs", "display_name": "HR", "sort_order": "1", "position_type": "B"}},
    {"stat": {"stat_id": 13, "enabled": "1", "name": "Runs Batted In", "display_name": "RBI", "sort_order": "1", "position_type": "B"}},
    {"stat": {"stat_id": 16, "enabled": "1", "name": "Stolen Bases", "display_name": "SB", "sort_order": "1", "position_type": "B"}},
    {"stat": {"stat_id": 3, "enabled": "1", "name": "Batting Average", "display_name": "AVG", "sort_order": "1", "position_type": "B"}},
    {"stat": {"stat_id": 28, "enabled": "1", "name": "Wins", "display_name": "W", "sort_order": "1", "position_type": "P"}},
    {"stat": {"stat_id": 32, "enabled": "1", "name": "Saves", "display_name": "SV", "sort_order": "1", "position_type": "P"}},
    {"stat": {"stat_id": 42, "enabled": "1", "name": "Strikeouts", "display_name": "K", "sort_order": "1", "position_type": "P"}},
    {"stat": {"stat_id": 26, "enabled": "1", "name": "Earned Run Average", "display_name": "ERA", "sort_order": "0", "position_type": "P"}},
    {"stat": {"stat_id": 27, "enabled": "1", "name": "WHIP", "display_name": "WHIP", "sort_order": "0", "position_type": "P"}}
  ]
}
```

The engine should extract `display_name` from each enabled stat entry. The `position_type` field (`"B"` for batters, `"P"` for pitchers) can be used to validate stat routing. The `sort_order` field indicates direction: `"1"` = higher is better, `"0"` = lower is better — this can cross-check against the `LOWER_IS_BETTER` set.

### FanGraphs Projection Column Names

FanGraphs projections are stored as flat dicts with CSV column headers as keys in `PlayerStats.stats` JSON:

**Batting (`stat_type='projections_batting'`):**
Counting: `PA`, `AB`, `H`, `HR`, `R`, `RBI`, `SB`, `BB`, `SO`, `1B`, `2B`, `3B`
Rate: `AVG`, `OBP`, `SLG`, `OPS`, `wRC+`, `ISO`, `BABIP`, `WAR`

**Pitching (`stat_type='projections_pitching'`):**
Counting: `W`, `L`, `SV`, `HLD`, `IP`, `SO`, `QS`, `GS`, `G`, `BB`, `ER`, `HR`
Rate: `ERA`, `WHIP`, `K/9`, `BB/9`, `FIP`, `K%`, `BB%`, `WAR`

### Yahoo-to-FanGraphs Mapping Dict

A `STAT_MAPPING` dict in the value engine maps Yahoo category display names to FanGraphs CSV keys. This is necessarily hardcoded domain knowledge — Yahoo and FanGraphs use different naming conventions.

```python
STAT_MAPPING: dict[str, str] = {
    # Batting counting
    "R": "R", "Runs (R)": "R",
    "HR": "HR", "Home Runs (HR)": "HR",
    "RBI": "RBI", "Runs Batted In (RBI)": "RBI",
    "SB": "SB", "Stolen Bases (SB)": "SB",
    "H": "H", "Hits (H)": "H",
    "BB": "BB", "Walks (BB)": "BB",
    # Batting rate
    "AVG": "AVG", "Batting Average (AVG)": "AVG",
    "OBP": "OBP", "On-base Percentage (OBP)": "OBP",
    "SLG": "SLG", "Slugging Percentage (SLG)": "SLG",
    "OPS": "OPS", "On-base + Slugging (OPS)": "OPS",
    # Pitching counting
    "W": "W", "Wins (W)": "W",
    "L": "L", "Losses (L)": "L",
    "SV": "SV", "Saves (SV)": "SV",
    "K": "SO", "Strikeouts (K)": "SO",  # Yahoo "K" → FanGraphs "SO"
    "QS": "QS", "Quality Starts (QS)": "QS",
    "HLD": "HLD", "Holds (HLD)": "HLD",
    "IP": "IP", "Innings Pitched (IP)": "IP",
    # Pitching rate
    "ERA": "ERA", "Earned Run Average (ERA)": "ERA",
    "WHIP": "WHIP",
    "K/9": "K/9",
}
```

At request time, the engine parses `scoring_categories` JSON, extracts `display_name` from each enabled stat entry, and maps each to a FanGraphs key via this dict. Unknown categories are logged and skipped.

### Stat Classification

Each stat is classified as counting or rate, and whether lower is better (for pitching rate stats). This is hardcoded alongside the mapping:

```python
RATE_STATS: set[str] = {"AVG", "OBP", "SLG", "OPS", "ERA", "WHIP", "K/9", "BB/9", "FIP"}
LOWER_IS_BETTER: set[str] = {"ERA", "WHIP", "BB/9"}
PITCHING_STATS: set[str] = {"W", "L", "SV", "HLD", "IP", "SO", "QS", "ERA", "WHIP", "K/9", "BB/9", "FIP", "BB"}
```

Rate stats use weighted averages (by PA for batting, IP for pitching) when aggregating team totals. Counting stats are summed.

Two-way players (e.g., Ohtani) may have both batting and pitching projections. Both are included — batting projections contribute to batting categories, pitching projections contribute to pitching categories. Routing uses Yahoo's `position_type` field (`"B"` or `"P"`) from the scoring categories as the primary signal, with the `PITCHING_STATS` set as fallback. Stats like `BB` that exist in both batting and pitching projections are routed to the correct source based on which category context they appear in.

## Value Engine Architecture

Located at `backend/analytics/category_value.py`. Three layers:

### Layer 1: Team Projection

For a given league, project each team's rest-of-season totals by summing FanGraphs ROS projections for every player on their roster.

- Counting stats: sum across roster players
- Rate stats: weighted average by PA (batters) or IP (pitchers) — uses `_get_num(stats, "PA")` or `_get_num(stats, "IP")` as weights
- Produces a dict per team: `{HR: 142, SB: 67, AVG: .261, ERA: 3.82, ...}`
- Uses `LeagueRoster` for all teams' rosters, `PlayerStats` for projections
- Scoring categories parsed from `UserLeague.scoring_categories` via `STAT_MAPPING`
- Uses the existing `_get_num(stats, *keys)` pattern for flexible key lookup

### Layer 2: Category Need Assessment

Compare your team's projected totals to the league. Output: `CategoryNeeds` dict mapping each scoring category to a 0.0–1.0 need weight.

**H2H format:**
- Compare projected totals to the league median in each category
- Categories where you're furthest below median (in the losing direction) get highest need
- For `LOWER_IS_BETTER` stats, "below median" means your value is higher than median
- Need score = how far below the win threshold, normalized to 0.0–1.0

**Roto format — gap-aware:**
- Rank your team in each category across all teams
- Calculate gap to next rank up (stats needed to gain a standings point)
- Calculate gap to next rank down (defensive — how close is the team below)
- Detect clustering — categories where a small improvement jumps multiple ranks
- Need score = `points_gainable_per_unit_of_improvement`, normalized to 0.0–1.0
- Categories where a small stat gain moves you up multiple ranks score higher than categories requiring massive gains for +1 rank

### Layer 3: Player Value Scoring

For each candidate player:

1. Look up their FanGraphs ROS projections per category
2. Compute marginal impact per category:
   - **Counting stats**: player's projected stat value (e.g., +18 HR) added to team total
   - **Rate stats**: recompute the team's weighted average with the player included — delta = new team rate minus old team rate. The magnitude depends on the player's volume (PA or IP) relative to the team's existing total.
3. Weight each category's impact by the need score from Layer 2
4. Sum weighted impacts and normalize to 0–100

**Normalization**: Normalize against the best available player in the current candidate pool. The highest raw weighted-impact sum maps to 100, zero maps to 0, and all other players are linearly scaled between. This means scores are relative to the current waiver pool — if the pool is weak, the "best" player still scores 100 but the absolute quality is lower. This is appropriate because the question is "who should I grab from what's available," not "how good is this player in absolute terms."

Players who improve your weakest categories score highest.

### Reusability for Trade Assessment (Future)

Layers 1 and 2 are player-agnostic — they describe your team's state. Layer 3 can score any player. For trade assessment:
- Score players you'd receive using current team needs
- Recompute needs without the players you'd give up
- Score incoming players against adjusted needs
- Compare total value exchanged for fairness assessment

## Data Model

No new database tables. Computed on-the-fly from existing data:

- `LeagueRoster` — all teams' rosters (player assignments)
- `LeagueTeam` — team metadata, `is_current_user` flag
- `PlayerStats` — FanGraphs projections (`stat_type = 'projections_batting'` or `'projections_pitching'`)
- `UserLeague` — `scoring_categories` (JSON), `format` ('head' or roto), `num_teams`

No caching for now. Projections change daily, rosters change infrequently.

## API Design

### New Endpoint: Team Analysis

```
GET /api/leagues/{league_id}/team-analysis
```

Response:
```json
{
  "league_format": "head",
  "scoring_categories": ["HR", "RBI", "R", "SB", "AVG", "W", "SV", "K", "ERA", "WHIP"],
  "my_team": {
    "team_name": "...",
    "projected_totals": {"HR": 142, "RBI": 410, "AVG": 0.261},
    "category_ranks": {"HR": 4, "RBI": 8, "AVG": 6},
    "category_needs": {"HR": 0.3, "RBI": 0.9, "AVG": 0.6}
  },
  "categories": [
    {
      "category": "HR",
      "my_value": 142,
      "league_avg": 155,
      "rank": 4,
      "need": 0.3,
      "gap_to_next": null,
      "gap_below": null,
      "points_available": null
    }
  ],
  "current_matchup": {
    "opponent": "Team Name",
    "category_comparison": [
      {"category": "HR", "my_projected": 12, "opp_projected": 9, "edge": "win"}
    ]
  }
}
```

Notes:
- `categories` is a single unified array. For roto leagues, `gap_to_next`, `gap_below`, and `points_available` are populated. For H2H leagues, those fields are `null`.
- `current_matchup` only populated for H2H leagues, `null` for roto. Opponent determined by calling `yahoo.client.get_matchup()` at request time to fetch the current week's H2H opponent from Yahoo's API.

### Enhanced Endpoint: Waivers

```
GET /api/waivers/{league_id}?position={position}
```

The existing response structure (position-grouped `positions` dict) is preserved. Each player object gains new fields:
```json
{
  "value_score": 78,
  "category_impact": {
    "HR": {"projected": 18, "impact": 12.5, "need": 0.3},
    "RBI": {"projected": 55, "impact": 22.0, "need": 0.9}
  }
}
```

Default sort within each position group changes to `value_score` descending. Existing projection data and all other fields remain unchanged.

### New Route File

`backend/api/routes/team_analysis.py` — serves the team analysis endpoint. Both routes share the same value engine in `backend/analytics/category_value.py`.

## Frontend Design

### Team Analysis Page (`/team-analysis`)

**Layout:**
- League selector at top (switches between leagues)
- Summary cards row: Biggest Need (red), Biggest Strength (green), Projected Standing
- Radar chart: your team shape vs. league average overlay, category labels include rank
- Category detail table below the chart

**Category detail table — H2H:**

| Category | Projected | League Avg | Rank | Need |
|----------|-----------|------------|------|------|
| RBI | 410 | 470 | 8th | High |

**Category detail table — Roto (gap-aware):**

| Category | Projected | Rank | Gap to Next (+1) | Gap Below (-1) | Pts Available |
|----------|-----------|------|-------------------|----------------|---------------|
| K | 1,180 | 4th | +22 K to 3rd | 15 K ahead of 5th | 1 pt |
| R | 680 | 5th | +8 R to 4th, +12 to 3rd | 20 R ahead of 6th | 2 pts |

**H2H matchup panel** (informational only):
- Current week's opponent (fetched from Yahoo API)
- Category-by-category projected comparison (win/lose/toss-up)
- Does NOT affect value scores

### Waivers Page Enhancements

**Collapsible category needs panel** at top of page:
- Categories displayed as chips/badges sorted by urgency
- Color-coded: red (high need), yellow (medium), green (low)
- Each chip shows category name, rank, and need level
- "View full analysis →" link to Team Analysis page
- Collapsible to save space once you've seen your needs

**Player table changes:**
- Value score (0-100) as first column, color-coded (green >70, yellow 40-70, gray <40)
- Default sort by value_score descending
- Click/expand a player row to reveal per-category impact breakdown
- Breakdown shows: each category's projected contribution, impact score, and need level
- Existing projection columns remain
- Existing position-grouped response structure preserved (additive fields only)

### Navigation

- New "Team Analysis" entry in the nav bar
- Waivers page needs panel links to Team Analysis

## Scope Boundaries

**In scope:**
- Value engine with three layers (projection, needs, scoring)
- Stat mapping dict (Yahoo → FanGraphs) with stat classification
- Team Analysis page with radar chart and detail table
- Waivers page needs panel and value score integration
- Both H2H and roto format support
- Gap-aware roto need scoring

**Out of scope (future):**
- Trade assessment feature (engine designed to support it)
- Recent performance blending (projections only for now)
- Advanced metrics from Baseball Savant
- Caching/precomputation of value scores
- Weekly matchup influence on waiver value
