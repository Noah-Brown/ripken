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

## Value Engine Architecture

Located at `backend/analytics/category_value.py`. Three layers:

### Layer 1: Team Projection

For a given league, project each team's rest-of-season totals by summing FanGraphs ROS projections for every player on their roster.

- Counting stats (HR, RBI, R, SB, W, SV, K): sum across roster
- Rate stats (AVG, OBP, ERA, WHIP): weighted average by PA (batters) or IP (pitchers)
- Produces a dict per team: `{HR: 142, SB: 67, AVG: .261, ERA: 3.82, ...}`
- Uses `LeagueRoster` for all teams' rosters, `PlayerStats` for projections
- Scoring categories sourced from `UserLeague.scoring_categories` (no hardcoding)

### Layer 2: Category Need Assessment

Compare your team's projected totals to the league. Output: `CategoryNeeds` dict mapping each scoring category to a 0.0–1.0 need weight.

**H2H format:**
- Compare projected totals to the league median in each category
- Categories where you're furthest below median (in the losing direction) get highest need
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
2. Compute marginal impact: how much do your team's projected totals improve in each category if you add this player?
3. Weight each category's impact by the need score from Layer 2
4. Sum weighted impacts and normalize to 0–100

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
  "league_comparison": [
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
  "roto_gaps": [
    {
      "category": "K",
      "my_value": 1180,
      "rank": 4,
      "gap_to_next_rank": 22,
      "gap_below": 15,
      "points_available": 1
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
- `roto_gaps` only populated for roto leagues, `null` for H2H
- `current_matchup` only populated for H2H leagues, `null` for roto

### Enhanced Endpoint: Waivers

```
GET /api/waivers/{league_id}?position={position}
```

Each player in the response gains:
```json
{
  "value_score": 78,
  "category_impact": {
    "HR": {"projected": 18, "impact": 12.5, "need": 0.3},
    "RBI": {"projected": 55, "impact": 22.0, "need": 0.9}
  }
}
```

Default sort changes to `value_score` descending. Existing projection data remains in the response.

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
- Current week's opponent
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

### Navigation

- New "Team Analysis" entry in the nav bar
- Waivers page needs panel links to Team Analysis

## Scope Boundaries

**In scope:**
- Value engine with three layers (projection, needs, scoring)
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
