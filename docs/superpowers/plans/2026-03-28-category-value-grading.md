# Category Value Grading Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a value engine that scores waiver players 0-100 based on how much they help your specific team's weak categories, with a dedicated Team Analysis page and enhanced waivers page.

**Architecture:** Three-layer analytics engine (team projection → category needs → player scoring) in a single module, exposed via two API endpoints (team-analysis and enhanced waivers), consumed by two frontend pages. Both H2H and roto formats supported with format-specific need calculations.

**Tech Stack:** Python/FastAPI (backend analytics + routes), SQLAlchemy async (data access), Next.js 14 + React 19 + Tailwind CSS v4 (frontend), SVG radar chart (no chart library).

**Spec:** `docs/superpowers/specs/2026-03-28-category-value-grading-design.md`

---

## File Structure

### New Files
- `backend/analytics/category_value.py` — Value engine: stat mapping, team projection, category needs, player scoring
- `backend/api/routes/team_analysis.py` — Team analysis API endpoint
- `backend/tests/test_category_value.py` — Unit tests for value engine
- `frontend/src/app/team-analysis/page.tsx` — Team Analysis page with radar chart

### Modified Files
- `backend/api/routes/waivers.py` — Add value_score and category_impact to player entries
- `backend/main.py` — Register team_analysis router
- `frontend/src/app/waivers/page.tsx` — Add needs panel, value score column, expandable breakdown
- `frontend/src/lib/api.ts` — Add TeamAnalysis types

---

## Task 1: Stat Mapping and Category Parsing

**Files:**
- Create: `backend/analytics/category_value.py`
- Create: `backend/tests/test_category_value.py`

This task builds the foundation: parsing Yahoo scoring categories and mapping them to FanGraphs projection keys.

- [ ] **Step 1: Write tests for stat mapping and category parsing**

```python
# backend/tests/test_category_value.py
"""Tests for category value engine."""

import json
import pytest

from backend.analytics.category_value import (
    LOWER_IS_BETTER,
    PITCHING_STATS,
    RATE_STATS,
    STAT_MAPPING,
    parse_scoring_categories,
)


SAMPLE_YAHOO_CATEGORIES = {
    "stats": [
        {"stat": {"stat_id": 7, "enabled": "1", "name": "Runs", "display_name": "R", "sort_order": "1", "position_type": "B"}},
        {"stat": {"stat_id": 12, "enabled": "1", "name": "Home Runs", "display_name": "HR", "sort_order": "1", "position_type": "B"}},
        {"stat": {"stat_id": 13, "enabled": "1", "name": "Runs Batted In", "display_name": "RBI", "sort_order": "1", "position_type": "B"}},
        {"stat": {"stat_id": 16, "enabled": "1", "name": "Stolen Bases", "display_name": "SB", "sort_order": "1", "position_type": "B"}},
        {"stat": {"stat_id": 3, "enabled": "1", "name": "Batting Average", "display_name": "AVG", "sort_order": "1", "position_type": "B"}},
        {"stat": {"stat_id": 28, "enabled": "1", "name": "Wins", "display_name": "W", "sort_order": "1", "position_type": "P"}},
        {"stat": {"stat_id": 32, "enabled": "1", "name": "Saves", "display_name": "SV", "sort_order": "1", "position_type": "P"}},
        {"stat": {"stat_id": 42, "enabled": "1", "name": "Strikeouts", "display_name": "K", "sort_order": "1", "position_type": "P"}},
        {"stat": {"stat_id": 26, "enabled": "1", "name": "Earned Run Average", "display_name": "ERA", "sort_order": "0", "position_type": "P"}},
        {"stat": {"stat_id": 27, "enabled": "1", "name": "WHIP", "display_name": "WHIP", "sort_order": "0", "position_type": "P"}},
    ]
}


class TestStatMapping:
    def test_yahoo_k_maps_to_fangraphs_so(self):
        assert STAT_MAPPING["K"] == "SO"

    def test_common_batting_stats_map_to_themselves(self):
        for stat in ["R", "HR", "RBI", "SB", "AVG", "OBP", "OPS"]:
            assert STAT_MAPPING[stat] == stat

    def test_common_pitching_stats_map_correctly(self):
        assert STAT_MAPPING["W"] == "W"
        assert STAT_MAPPING["SV"] == "SV"
        assert STAT_MAPPING["ERA"] == "ERA"
        assert STAT_MAPPING["WHIP"] == "WHIP"

    def test_era_and_whip_are_lower_is_better(self):
        assert "ERA" in LOWER_IS_BETTER
        assert "WHIP" in LOWER_IS_BETTER
        assert "HR" not in LOWER_IS_BETTER

    def test_rate_stats_identified(self):
        assert "AVG" in RATE_STATS
        assert "ERA" in RATE_STATS
        assert "HR" not in RATE_STATS

    def test_pitching_stats_identified(self):
        assert "SO" in PITCHING_STATS
        assert "ERA" in PITCHING_STATS
        assert "HR" not in PITCHING_STATS


class TestParseScoringCategories:
    def test_parses_yahoo_json_structure(self):
        cats = parse_scoring_categories(json.dumps(SAMPLE_YAHOO_CATEGORIES))
        display_names = [c["display_name"] for c in cats]
        assert "R" in display_names
        assert "HR" in display_names
        assert "ERA" in display_names

    def test_maps_to_fangraphs_keys(self):
        cats = parse_scoring_categories(json.dumps(SAMPLE_YAHOO_CATEGORIES))
        fg_keys = {c["fg_key"] for c in cats}
        assert "SO" in fg_keys  # K -> SO
        assert "R" in fg_keys
        assert "ERA" in fg_keys

    def test_includes_position_type(self):
        cats = parse_scoring_categories(json.dumps(SAMPLE_YAHOO_CATEGORIES))
        hr_cat = next(c for c in cats if c["display_name"] == "HR")
        assert hr_cat["position_type"] == "B"
        era_cat = next(c for c in cats if c["display_name"] == "ERA")
        assert era_cat["position_type"] == "P"

    def test_includes_is_rate_and_lower_is_better(self):
        cats = parse_scoring_categories(json.dumps(SAMPLE_YAHOO_CATEGORIES))
        era_cat = next(c for c in cats if c["display_name"] == "ERA")
        assert era_cat["is_rate"] is True
        assert era_cat["lower_is_better"] is True
        hr_cat = next(c for c in cats if c["display_name"] == "HR")
        assert hr_cat["is_rate"] is False
        assert hr_cat["lower_is_better"] is False

    def test_skips_unknown_categories(self):
        data = {
            "stats": [
                {"stat": {"stat_id": 999, "enabled": "1", "name": "Weird Stat", "display_name": "WRD", "sort_order": "1", "position_type": "B"}},
                {"stat": {"stat_id": 7, "enabled": "1", "name": "Runs", "display_name": "R", "sort_order": "1", "position_type": "B"}},
            ]
        }
        cats = parse_scoring_categories(json.dumps(data))
        assert len(cats) == 1
        assert cats[0]["display_name"] == "R"

    def test_returns_empty_for_invalid_json(self):
        cats = parse_scoring_categories("not json")
        assert cats == []

    def test_returns_empty_for_none(self):
        cats = parse_scoring_categories(None)
        assert cats == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nbrown/projects/ripken && python -m pytest backend/tests/test_category_value.py -v
```

Expected: ImportError — `backend.analytics.category_value` does not exist.

- [ ] **Step 3: Implement stat mapping and category parsing**

```python
# backend/analytics/category_value.py
"""Category value engine — scores players by team need.

Three layers:
1. Team Projection: sum FanGraphs ROS projections per roster
2. Category Needs: identify weak categories (H2H median / roto gap-aware)
3. Player Value: score candidates 0-100 by weighted category impact
"""

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import (
    LeagueRoster,
    LeagueTeam,
    Player,
    PlayerStats,
    UserLeague,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stat mapping: Yahoo display_name -> FanGraphs CSV column key
# ---------------------------------------------------------------------------

STAT_MAPPING: dict[str, str] = {
    # Batting counting
    "H/AB": None,  # Display-only composite stat, not a scoring category — skip
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
    "K": "SO", "Strikeouts (K)": "SO",
    "QS": "QS", "Quality Starts (QS)": "QS",
    "HLD": "HLD", "Holds (HLD)": "HLD",
    "IP": "IP", "Innings Pitched (IP)": "IP",
    # Pitching rate
    "ERA": "ERA", "Earned Run Average (ERA)": "ERA",
    "WHIP": "WHIP",
    "K/9": "K/9",
}

RATE_STATS: set[str] = {"AVG", "OBP", "SLG", "OPS", "ERA", "WHIP", "K/9", "BB/9", "FIP"}
LOWER_IS_BETTER: set[str] = {"ERA", "WHIP", "BB/9"}
PITCHING_STATS: set[str] = {
    "W", "L", "SV", "HLD", "IP", "SO", "QS",
    "ERA", "WHIP", "K/9", "BB/9", "FIP", "BB",
}


# ---------------------------------------------------------------------------
# Category parsing
# ---------------------------------------------------------------------------

def parse_scoring_categories(scoring_categories_json: str | None) -> list[dict]:
    """Parse Yahoo scoring_categories JSON into a list of category dicts.

    Returns list of:
        {
            "display_name": "HR",
            "fg_key": "HR",
            "position_type": "B",
            "is_rate": False,
            "lower_is_better": False,
        }
    """
    if not scoring_categories_json:
        return []
    try:
        data = json.loads(scoring_categories_json)
    except (json.JSONDecodeError, TypeError):
        return []

    stats_list = data.get("stats", [])
    categories = []
    for entry in stats_list:
        stat = entry.get("stat", {})
        display_name = stat.get("display_name", "")
        if not display_name or stat.get("enabled") != "1":
            continue

        fg_key = STAT_MAPPING.get(display_name)
        if fg_key is None:
            if display_name not in STAT_MAPPING:
                logger.warning("Unknown Yahoo category '%s' — skipping", display_name)
            # Explicitly mapped to None (e.g., H/AB) means skip silently
            continue

        categories.append({
            "display_name": display_name,
            "fg_key": fg_key,
            "position_type": stat.get("position_type", "B"),
            "is_rate": fg_key in RATE_STATS,
            "lower_is_better": fg_key in LOWER_IS_BETTER,
        })

    return categories
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/nbrown/projects/ripken && python -m pytest backend/tests/test_category_value.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/category_value.py backend/tests/test_category_value.py
git commit -m "feat: add stat mapping and Yahoo category parsing for value engine"
```

---

## Task 2: Team Projection (Layer 1)

**Files:**
- Modify: `backend/analytics/category_value.py`
- Modify: `backend/tests/test_category_value.py`

Project ROS totals for all teams in a league from FanGraphs projections.

- [ ] **Step 1: Write tests for team projection**

Add to `backend/tests/test_category_value.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch
from backend.analytics.category_value import project_all_teams


def _make_player_stats(player_id: int, stat_type: str, stats: dict) -> MagicMock:
    ps = MagicMock()
    ps.player_id = player_id
    ps.stat_type = stat_type
    ps.stats = json.dumps(stats)
    return ps


def _make_roster_row(player_id: int, team_key: str, team_name: str) -> MagicMock:
    r = MagicMock()
    r.player_id = player_id
    r.yahoo_team_key = team_key
    r.yahoo_team_name = team_name
    return r


def _make_player(player_id: int, position: str) -> MagicMock:
    p = MagicMock()
    p.id = player_id
    p.position = position
    return p


BATTING_CATS = [
    {"display_name": "HR", "fg_key": "HR", "position_type": "B", "is_rate": False, "lower_is_better": False},
    {"display_name": "AVG", "fg_key": "AVG", "position_type": "B", "is_rate": True, "lower_is_better": False},
]

PITCHING_CATS = [
    {"display_name": "W", "fg_key": "W", "position_type": "P", "is_rate": False, "lower_is_better": False},
    {"display_name": "ERA", "fg_key": "ERA", "position_type": "P", "is_rate": True, "lower_is_better": True},
]


class TestProjectAllTeams:
    @pytest.mark.asyncio
    async def test_sums_counting_stats(self):
        """Two hitters on same team: HR should sum."""
        rosters = [
            _make_roster_row(1, "t1", "Team A"),
            _make_roster_row(2, "t1", "Team A"),
        ]
        players = {1: _make_player(1, "OF"), 2: _make_player(2, "1B")}
        projections = {
            1: {"projections_batting": {"HR": 20, "AVG": 0.280, "PA": 500}},
            2: {"projections_batting": {"HR": 15, "AVG": 0.260, "PA": 400}},
        }

        result = project_all_teams(rosters, players, projections, BATTING_CATS)
        assert "t1" in result
        assert result["t1"]["HR"] == 35

    @pytest.mark.asyncio
    async def test_weights_rate_stats_by_pa(self):
        """AVG should be PA-weighted average, not simple mean."""
        rosters = [
            _make_roster_row(1, "t1", "Team A"),
            _make_roster_row(2, "t1", "Team A"),
        ]
        players = {1: _make_player(1, "OF"), 2: _make_player(2, "1B")}
        projections = {
            1: {"projections_batting": {"AVG": 0.300, "PA": 600}},
            2: {"projections_batting": {"AVG": 0.200, "PA": 400}},
        }

        result = project_all_teams(rosters, players, projections, BATTING_CATS)
        # Weighted: (0.300*600 + 0.200*400) / (600+400) = 260/1000 = 0.260
        assert abs(result["t1"]["AVG"] - 0.260) < 0.001

    @pytest.mark.asyncio
    async def test_pitching_rate_stats_weighted_by_ip(self):
        """ERA should be IP-weighted."""
        rosters = [
            _make_roster_row(3, "t1", "Team A"),
            _make_roster_row(4, "t1", "Team A"),
        ]
        players = {3: _make_player(3, "SP"), 4: _make_player(4, "RP")}
        projections = {
            3: {"projections_pitching": {"W": 12, "ERA": 3.00, "IP": 180}},
            4: {"projections_pitching": {"W": 5, "ERA": 4.50, "IP": 60}},
        }

        result = project_all_teams(rosters, players, projections, PITCHING_CATS)
        assert result["t1"]["W"] == 17
        # Weighted ERA: (3.00*180 + 4.50*60) / (180+60) = 810/240 = 3.375
        assert abs(result["t1"]["ERA"] - 3.375) < 0.001

    @pytest.mark.asyncio
    async def test_multiple_teams_separated(self):
        rosters = [
            _make_roster_row(1, "t1", "Team A"),
            _make_roster_row(2, "t2", "Team B"),
        ]
        players = {1: _make_player(1, "OF"), 2: _make_player(2, "OF")}
        projections = {
            1: {"projections_batting": {"HR": 30, "AVG": 0.300, "PA": 500}},
            2: {"projections_batting": {"HR": 10, "AVG": 0.250, "PA": 500}},
        }

        result = project_all_teams(rosters, players, projections, BATTING_CATS)
        assert result["t1"]["HR"] == 30
        assert result["t2"]["HR"] == 10

    @pytest.mark.asyncio
    async def test_skips_players_without_projections(self):
        rosters = [
            _make_roster_row(1, "t1", "Team A"),
            _make_roster_row(99, "t1", "Team A"),  # no projection
        ]
        players = {1: _make_player(1, "OF"), 99: _make_player(99, "OF")}
        projections = {
            1: {"projections_batting": {"HR": 20, "AVG": 0.280, "PA": 500}},
        }

        result = project_all_teams(rosters, players, projections, BATTING_CATS)
        assert result["t1"]["HR"] == 20
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nbrown/projects/ripken && python -m pytest backend/tests/test_category_value.py::TestProjectAllTeams -v
```

Expected: ImportError — `project_all_teams` not defined.

- [ ] **Step 3: Implement team projection**

Add to `backend/analytics/category_value.py`:

```python
def _get_num(stats: dict, *keys: str) -> float | None:
    """Try multiple key names to find a numeric stat."""
    for key in keys:
        val = stats.get(key)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return None


def project_all_teams(
    rosters: list,
    players: dict[int, Any],
    projections: dict[int, dict],
    categories: list[dict],
) -> dict[str, dict[str, float]]:
    """Project ROS totals for every team in the league.

    Args:
        rosters: LeagueRoster rows with player_id, yahoo_team_key, yahoo_team_name
        players: player_id -> Player object (needs .position)
        projections: player_id -> {stat_type: stats_dict} — keyed by stat_type
            to support two-way players (e.g., Ohtani has both batting and pitching)
        categories: parsed scoring categories from parse_scoring_categories()

    Returns:
        team_key -> {fg_key: projected_value, ...}
    """
    # Group roster by team
    team_players: dict[str, list[int]] = {}
    for row in rosters:
        if row.player_id is None:
            continue
        key = row.yahoo_team_key
        if key not in team_players:
            team_players[key] = []
        team_players[key].append(row.player_id)

    result: dict[str, dict[str, float]] = {}

    for team_key, player_ids in team_players.items():
        team_totals: dict[str, float] = {}
        # Accumulators for rate stats: fg_key -> (weighted_sum, weight_sum)
        rate_accum: dict[str, tuple[float, float]] = {}

        for pid in player_ids:
            player = players.get(pid)
            player_projs = projections.get(pid)
            if not player or not player_projs:
                continue

            for cat in categories:
                fg_key = cat["fg_key"]
                cat_is_pitching = cat["position_type"] == "P"

                # Pick the correct projection source for this category
                if cat_is_pitching:
                    proj = player_projs.get("projections_pitching", {})
                else:
                    proj = player_projs.get("projections_batting", {})

                if not proj:
                    continue

                val = _get_num(proj, fg_key, fg_key.lower())
                if val is None:
                    continue

                if cat["is_rate"]:
                    # Weight by PA (batters) or IP (pitchers)
                    if cat_is_pitching:
                        weight = _get_num(proj, "IP", "ip") or 0
                    else:
                        weight = _get_num(proj, "PA", "pa") or 0
                    if weight > 0:
                        prev = rate_accum.get(fg_key, (0.0, 0.0))
                        rate_accum[fg_key] = (prev[0] + val * weight, prev[1] + weight)
                else:
                    team_totals[fg_key] = team_totals.get(fg_key, 0) + val

        # Resolve rate stats
        for fg_key, (weighted_sum, weight_sum) in rate_accum.items():
            if weight_sum > 0:
                team_totals[fg_key] = weighted_sum / weight_sum

        result[team_key] = team_totals

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/nbrown/projects/ripken && python -m pytest backend/tests/test_category_value.py::TestProjectAllTeams -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/category_value.py backend/tests/test_category_value.py
git commit -m "feat: add team projection layer for category value engine"
```

---

## Task 3: Category Need Assessment (Layer 2)

**Files:**
- Modify: `backend/analytics/category_value.py`
- Modify: `backend/tests/test_category_value.py`

Calculate category need scores for both H2H and roto formats.

- [ ] **Step 1: Write tests for H2H needs**

Add to `backend/tests/test_category_value.py`:

```python
from backend.analytics.category_value import compute_category_needs_h2h, compute_category_needs_roto


class TestCategoryNeedsH2H:
    def test_worst_category_gets_highest_need(self):
        """Team ranked last in HR should have highest need for HR."""
        team_totals = {"HR": 100, "SB": 80}
        all_teams = {
            "t1": {"HR": 100, "SB": 80},
            "t2": {"HR": 150, "SB": 50},
            "t3": {"HR": 130, "SB": 40},
        }
        cats = [
            {"fg_key": "HR", "is_rate": False, "lower_is_better": False, "display_name": "HR", "position_type": "B"},
            {"fg_key": "SB", "is_rate": False, "lower_is_better": False, "display_name": "SB", "position_type": "B"},
        ]
        needs = compute_category_needs_h2h(team_totals, all_teams, cats)
        assert needs["HR"] > needs["SB"]  # HR is worst category

    def test_lower_is_better_reversed(self):
        """Team with highest ERA should have highest need for ERA."""
        team_totals = {"ERA": 5.00, "WHIP": 1.10}
        all_teams = {
            "t1": {"ERA": 5.00, "WHIP": 1.10},
            "t2": {"ERA": 3.50, "WHIP": 1.30},
            "t3": {"ERA": 4.00, "WHIP": 1.20},
        }
        cats = [
            {"fg_key": "ERA", "is_rate": True, "lower_is_better": True, "display_name": "ERA", "position_type": "P"},
            {"fg_key": "WHIP", "is_rate": True, "lower_is_better": True, "display_name": "WHIP", "position_type": "P"},
        ]
        needs = compute_category_needs_h2h(team_totals, all_teams, cats)
        assert needs["ERA"] > needs["WHIP"]  # ERA is worse (higher = worse)

    def test_best_category_gets_zero_or_low_need(self):
        team_totals = {"HR": 200, "SB": 10}
        all_teams = {
            "t1": {"HR": 200, "SB": 10},
            "t2": {"HR": 100, "SB": 50},
        }
        cats = [
            {"fg_key": "HR", "is_rate": False, "lower_is_better": False, "display_name": "HR", "position_type": "B"},
            {"fg_key": "SB", "is_rate": False, "lower_is_better": False, "display_name": "SB", "position_type": "B"},
        ]
        needs = compute_category_needs_h2h(team_totals, all_teams, cats)
        assert needs["HR"] < 0.1  # Best in league, minimal need

    def test_needs_between_zero_and_one(self):
        team_totals = {"HR": 100, "SB": 50}
        all_teams = {"t1": {"HR": 100, "SB": 50}, "t2": {"HR": 150, "SB": 30}}
        cats = [
            {"fg_key": "HR", "is_rate": False, "lower_is_better": False, "display_name": "HR", "position_type": "B"},
            {"fg_key": "SB", "is_rate": False, "lower_is_better": False, "display_name": "SB", "position_type": "B"},
        ]
        needs = compute_category_needs_h2h(team_totals, all_teams, cats)
        for v in needs.values():
            assert 0.0 <= v <= 1.0


class TestCategoryNeedsRoto:
    def test_gap_aware_scoring(self):
        """Category where small gain jumps multiple ranks > category with huge gap."""
        # SB: team is 4th, teams above at 52, 53, 54 — small gap, 3 pts available
        # HR: team is 4th, team above at 200 — huge gap, 1 pt available
        all_teams = {
            "t1": {"SB": 50, "HR": 100},
            "t2": {"SB": 52, "HR": 200},
            "t3": {"SB": 53, "HR": 180},
            "t4": {"SB": 54, "HR": 160},
        }
        cats = [
            {"fg_key": "SB", "is_rate": False, "lower_is_better": False, "display_name": "SB", "position_type": "B"},
            {"fg_key": "HR", "is_rate": False, "lower_is_better": False, "display_name": "HR", "position_type": "B"},
        ]
        needs = compute_category_needs_roto("t1", all_teams, cats)
        assert needs["SB"] > needs["HR"]  # SB has better ROI

    def test_first_place_category_low_need(self):
        all_teams = {
            "t1": {"HR": 200},
            "t2": {"HR": 100},
            "t3": {"HR": 80},
        }
        cats = [{"fg_key": "HR", "is_rate": False, "lower_is_better": False, "display_name": "HR", "position_type": "B"}]
        needs = compute_category_needs_roto("t1", all_teams, cats)
        assert needs["HR"] < 0.2

    def test_lower_is_better_ranks_correctly(self):
        """Lowest ERA should rank 1st, not last."""
        all_teams = {
            "t1": {"ERA": 3.00},
            "t2": {"ERA": 4.00},
            "t3": {"ERA": 5.00},
        }
        cats = [{"fg_key": "ERA", "is_rate": True, "lower_is_better": True, "display_name": "ERA", "position_type": "P"}]
        needs = compute_category_needs_roto("t1", all_teams, cats)
        assert needs["ERA"] < 0.2  # 1st place, low need

    def test_needs_between_zero_and_one(self):
        all_teams = {
            "t1": {"HR": 100, "SB": 50},
            "t2": {"HR": 150, "SB": 30},
            "t3": {"HR": 120, "SB": 60},
        }
        cats = [
            {"fg_key": "HR", "is_rate": False, "lower_is_better": False, "display_name": "HR", "position_type": "B"},
            {"fg_key": "SB", "is_rate": False, "lower_is_better": False, "display_name": "SB", "position_type": "B"},
        ]
        needs = compute_category_needs_roto("t1", all_teams, cats)
        for v in needs.values():
            assert 0.0 <= v <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nbrown/projects/ripken && python -m pytest backend/tests/test_category_value.py -k "Needs" -v
```

Expected: ImportError.

- [ ] **Step 3: Implement category needs for H2H**

Add to `backend/analytics/category_value.py`:

```python
import statistics


def compute_category_needs_h2h(
    my_totals: dict[str, float],
    all_teams: dict[str, dict[str, float]],
    categories: list[dict],
) -> dict[str, float]:
    """Compute 0-1 need scores for H2H format.

    Need = how far below the league median (in the losing direction).
    """
    needs: dict[str, float] = {}
    all_values = list(all_teams.values())

    for cat in categories:
        fg_key = cat["fg_key"]
        my_val = my_totals.get(fg_key, 0)
        league_vals = [t.get(fg_key, 0) for t in all_values]
        if not league_vals:
            needs[fg_key] = 0.5
            continue

        median = statistics.median(league_vals)
        val_range = max(league_vals) - min(league_vals)
        if val_range == 0:
            needs[fg_key] = 0.0
            continue

        if cat["lower_is_better"]:
            # Higher value = worse, so distance above median = need
            distance = (my_val - median) / val_range
        else:
            # Lower value = worse, so distance below median = need
            distance = (median - my_val) / val_range

        # Clamp to 0-1: negative distance means you're above median (low need)
        needs[fg_key] = max(0.0, min(1.0, distance))

    return needs
```

- [ ] **Step 4: Implement category needs for roto (gap-aware)**

Add to `backend/analytics/category_value.py`:

```python
def compute_category_needs_roto(
    my_team_key: str,
    all_teams: dict[str, dict[str, float]],
    categories: list[dict],
) -> dict[str, float]:
    """Compute 0-1 need scores for roto format using gap-aware ranking.

    Need = points_gainable_per_unit_of_improvement, normalized.
    Categories where a small stat improvement jumps multiple ranks score highest.
    """
    needs: dict[str, float] = {}
    raw_scores: dict[str, float] = {}

    for cat in categories:
        fg_key = cat["fg_key"]
        # Gather all team values for this category
        team_vals: list[tuple[str, float]] = []
        for tk, totals in all_teams.items():
            team_vals.append((tk, totals.get(fg_key, 0)))

        # Sort: higher is better by default, reverse for lower_is_better
        reverse = not cat["lower_is_better"]
        team_vals.sort(key=lambda x: x[1], reverse=reverse)

        # Find my rank (1-indexed)
        my_val = all_teams.get(my_team_key, {}).get(fg_key, 0)
        my_rank = next(
            (i + 1 for i, (tk, _) in enumerate(team_vals) if tk == my_team_key),
            len(team_vals),
        )

        if my_rank == 1:
            # Already first, low need
            raw_scores[fg_key] = 0.0
            continue

        # Calculate gap to teams above and points available
        # "Above" means better-ranked teams (lower rank number)
        # gap_to_next = gap to the team immediately above (fixed threshold)
        # points_available = how many ranks you'd gain if you improved by that gap
        next_team_val = team_vals[my_rank - 2][1]
        gap_to_next = abs(next_team_val - my_val)

        if gap_to_next == 0:
            # Tied — even tiny improvement gains a rank
            raw_scores[fg_key] = float(len(team_vals))  # high priority
            continue

        # Count teams within 3x the gap_to_next (clustered above)
        points_available = 0
        for i in range(my_rank - 2, -1, -1):
            other_val = team_vals[i][1]
            gap = abs(other_val - my_val)
            if gap <= gap_to_next * 3:
                points_available += 1
            else:
                break

        if gap_to_next == float("inf"):
            raw_scores[fg_key] = 0.0
        else:
            # Score = points available per unit of gap
            raw_scores[fg_key] = points_available / gap_to_next

    # Normalize raw scores to 0-1
    max_raw = max(raw_scores.values()) if raw_scores else 1.0
    if max_raw == 0:
        needs = {k: 0.0 for k in raw_scores}
    else:
        needs = {k: v / max_raw for k, v in raw_scores.items()}

    return needs
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/nbrown/projects/ripken && python -m pytest backend/tests/test_category_value.py -k "Needs" -v
```

Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add backend/analytics/category_value.py backend/tests/test_category_value.py
git commit -m "feat: add category need assessment for H2H and roto formats"
```

---

## Task 4: Player Value Scoring (Layer 3)

**Files:**
- Modify: `backend/analytics/category_value.py`
- Modify: `backend/tests/test_category_value.py`

Score candidate players 0-100 by how much they improve weak categories.

- [ ] **Step 1: Write tests for player scoring**

Add to `backend/tests/test_category_value.py`:

```python
from backend.analytics.category_value import score_players


class TestScorePlayers:
    def test_player_helping_high_need_category_scores_higher(self):
        """Player with HR (high need) > player with SB (low need)."""
        needs = {"HR": 0.9, "SB": 0.1}
        cats = [
            {"fg_key": "HR", "is_rate": False, "lower_is_better": False, "display_name": "HR", "position_type": "B"},
            {"fg_key": "SB", "is_rate": False, "lower_is_better": False, "display_name": "SB", "position_type": "B"},
        ]
        my_totals = {"HR": 100, "SB": 80}
        my_rate_accum = {}
        candidates = {
            10: {"projections_batting": {"HR": 30, "SB": 5, "PA": 500}},
            11: {"projections_batting": {"HR": 5, "SB": 30, "PA": 500}},
        }
        players = {10: _make_player(10, "OF"), 11: _make_player(11, "OF")}

        scores = score_players(candidates, players, needs, cats, my_totals, my_rate_accum)
        assert scores[10]["value_score"] > scores[11]["value_score"]

    def test_best_player_gets_100(self):
        needs = {"HR": 1.0}
        cats = [{"fg_key": "HR", "is_rate": False, "lower_is_better": False, "display_name": "HR", "position_type": "B"}]
        my_totals = {"HR": 100}
        candidates = {
            10: {"projections_batting": {"HR": 30, "PA": 500}},
            11: {"projections_batting": {"HR": 10, "PA": 400}},
        }
        players = {10: _make_player(10, "OF"), 11: _make_player(11, "OF")}

        scores = score_players(candidates, players, needs, cats, my_totals, {})
        assert scores[10]["value_score"] == 100
        assert scores[11]["value_score"] < 100

    def test_includes_category_impact_breakdown(self):
        needs = {"HR": 0.8, "SB": 0.2}
        cats = [
            {"fg_key": "HR", "is_rate": False, "lower_is_better": False, "display_name": "HR", "position_type": "B"},
            {"fg_key": "SB", "is_rate": False, "lower_is_better": False, "display_name": "SB", "position_type": "B"},
        ]
        my_totals = {"HR": 100, "SB": 80}
        candidates = {10: {"projections_batting": {"HR": 25, "SB": 10, "PA": 500}}}
        players = {10: _make_player(10, "OF")}

        scores = score_players(candidates, players, needs, cats, my_totals, {})
        impact = scores[10]["category_impact"]
        assert "HR" in impact
        assert "SB" in impact
        assert impact["HR"]["projected"] == 25
        assert impact["HR"]["need"] == 0.8

    def test_rate_stat_impact(self):
        """Adding a high-AVG player should improve team AVG."""
        needs = {"AVG": 0.8}
        cats = [{"fg_key": "AVG", "is_rate": True, "lower_is_better": False, "display_name": "AVG", "position_type": "B"}]
        my_totals = {"AVG": 0.250}
        my_rate_accum = {"AVG": (0.250 * 3000, 3000)}  # team: .250 over 3000 PA
        candidates = {
            10: {"projections_batting": {"AVG": 0.300, "PA": 500}},
            11: {"projections_batting": {"AVG": 0.220, "PA": 500}},
        }
        players = {10: _make_player(10, "OF"), 11: _make_player(11, "OF")}

        scores = score_players(candidates, players, needs, cats, my_totals, my_rate_accum)
        assert scores[10]["value_score"] > scores[11]["value_score"]

    def test_empty_candidates_returns_empty(self):
        scores = score_players({}, {}, {"HR": 1.0}, [], {}, {})
        assert scores == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nbrown/projects/ripken && python -m pytest backend/tests/test_category_value.py::TestScorePlayers -v
```

Expected: ImportError.

- [ ] **Step 3: Implement player scoring**

Add to `backend/analytics/category_value.py`:

```python
def score_players(
    candidates: dict[int, dict[str, dict]],
    players: dict[int, Any],
    needs: dict[str, float],
    categories: list[dict],
    my_totals: dict[str, float],
    my_rate_accum: dict[str, tuple[float, float]],
) -> dict[int, dict]:
    """Score candidate players 0-100 by weighted category impact.

    Args:
        candidates: player_id -> {stat_type: stats_dict} (same format as projections)
        players: player_id -> Player object
        needs: fg_key -> 0-1 need weight
        categories: parsed scoring categories
        my_totals: my team's projected totals
        my_rate_accum: fg_key -> (weighted_sum, weight_sum) for rate stat impact

    Returns:
        player_id -> {"value_score": int, "category_impact": {...}}
    """
    if not candidates:
        return {}

    raw_results: dict[int, dict] = {}

    for pid, player_projs in candidates.items():
        player = players.get(pid)
        if not player:
            continue

        weighted_sum = 0.0
        impact_breakdown: dict[str, dict] = {}

        for cat in categories:
            fg_key = cat["fg_key"]
            cat_is_pitching = cat["position_type"] == "P"

            # Pick the correct projection source for this category
            proj = player_projs.get(
                "projections_pitching" if cat_is_pitching else "projections_batting", {}
            )
            if not proj:
                continue

            val = _get_num(proj, fg_key, fg_key.lower())
            if val is None:
                continue

            need = needs.get(fg_key, 0)

            if cat["is_rate"]:
                # Impact = change in team's weighted average when adding this player
                weight_key = "IP" if cat_is_pitching else "PA"
                player_weight = _get_num(proj, weight_key, weight_key.lower()) or 0
                if player_weight <= 0:
                    continue
                prev = my_rate_accum.get(fg_key, (0.0, 0.0))
                old_avg = prev[0] / prev[1] if prev[1] > 0 else 0
                new_avg = (prev[0] + val * player_weight) / (prev[1] + player_weight)
                impact = new_avg - old_avg
                if cat["lower_is_better"]:
                    impact = -impact  # Negative ERA change is positive impact
            else:
                impact = val

            weighted_impact = impact * need
            weighted_sum += weighted_impact

            impact_breakdown[cat["display_name"]] = {
                "projected": round(val, 3) if cat["is_rate"] else round(val, 1),
                "impact": round(impact, 3) if cat["is_rate"] else round(impact, 1),
                "need": round(need, 2),
            }

        raw_results[pid] = {
            "raw_score": weighted_sum,
            "category_impact": impact_breakdown,
        }

    # Normalize to 0-100
    max_raw = max((r["raw_score"] for r in raw_results.values()), default=0)
    results: dict[int, dict] = {}
    for pid, r in raw_results.items():
        if max_raw > 0:
            score = round((r["raw_score"] / max_raw) * 100)
        else:
            score = 0
        score = max(0, min(100, score))
        results[pid] = {
            "value_score": score,
            "category_impact": r["category_impact"],
        }

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/nbrown/projects/ripken && python -m pytest backend/tests/test_category_value.py::TestScorePlayers -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/category_value.py backend/tests/test_category_value.py
git commit -m "feat: add player value scoring layer with category impact breakdown"
```

---

## Task 5: Orchestration — Full Pipeline Functions

**Files:**
- Modify: `backend/analytics/category_value.py`
- Modify: `backend/tests/test_category_value.py`

Add the top-level async functions that wire Layers 1-3 together with DB queries.

- [ ] **Step 1: Write test for roto gap detail calculation**

Add to `backend/tests/test_category_value.py`:

```python
from backend.analytics.category_value import compute_roto_gap_details


class TestRotoGapDetails:
    def test_returns_gap_to_next_and_below(self):
        all_teams = {
            "t1": {"HR": 100},
            "t2": {"HR": 120},
            "t3": {"HR": 80},
        }
        cats = [{"fg_key": "HR", "is_rate": False, "lower_is_better": False, "display_name": "HR", "position_type": "B"}]
        details = compute_roto_gap_details("t1", all_teams, cats)
        hr = details["HR"]
        assert hr["rank"] == 2
        assert hr["gap_to_next"] == 20  # need 20 more HR to catch t2
        assert hr["gap_below"] == 20   # t3 is 20 behind
        assert hr["points_available"] == 1

    def test_first_place_has_no_gap_to_next(self):
        all_teams = {
            "t1": {"HR": 200},
            "t2": {"HR": 100},
        }
        cats = [{"fg_key": "HR", "is_rate": False, "lower_is_better": False, "display_name": "HR", "position_type": "B"}]
        details = compute_roto_gap_details("t1", all_teams, cats)
        assert details["HR"]["rank"] == 1
        assert details["HR"]["gap_to_next"] is None

    def test_lower_is_better_ranks_correctly(self):
        all_teams = {
            "t1": {"ERA": 3.50},
            "t2": {"ERA": 3.00},
            "t3": {"ERA": 4.00},
        }
        cats = [{"fg_key": "ERA", "is_rate": True, "lower_is_better": True, "display_name": "ERA", "position_type": "P"}]
        details = compute_roto_gap_details("t1", all_teams, cats)
        assert details["ERA"]["rank"] == 2  # 2nd best ERA
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/nbrown/projects/ripken && python -m pytest backend/tests/test_category_value.py::TestRotoGapDetails -v
```

- [ ] **Step 3: Implement roto gap details and orchestration functions**

Add to `backend/analytics/category_value.py`:

```python
def compute_roto_gap_details(
    my_team_key: str,
    all_teams: dict[str, dict[str, float]],
    categories: list[dict],
) -> dict[str, dict]:
    """Compute roto gap details for each category.

    Returns fg_key -> {rank, gap_to_next, gap_below, points_available}
    """
    details: dict[str, dict] = {}

    for cat in categories:
        fg_key = cat["fg_key"]
        team_vals: list[tuple[str, float]] = [
            (tk, totals.get(fg_key, 0)) for tk, totals in all_teams.items()
        ]
        reverse = not cat["lower_is_better"]
        team_vals.sort(key=lambda x: x[1], reverse=reverse)

        my_idx = next(
            (i for i, (tk, _) in enumerate(team_vals) if tk == my_team_key),
            len(team_vals) - 1,
        )
        my_rank = my_idx + 1
        my_val = all_teams.get(my_team_key, {}).get(fg_key, 0)

        gap_to_next = None
        gap_below = None
        points_available = 0

        if my_idx > 0:
            next_val = team_vals[my_idx - 1][1]
            gap_to_next = round(abs(next_val - my_val), 3)
            # Count teams within 3x the gap_to_next (clustered above)
            for i in range(my_idx - 1, -1, -1):
                other_val = team_vals[i][1]
                gap = abs(other_val - my_val)
                if gap <= gap_to_next * 3:
                    points_available += 1
                else:
                    break

        if my_idx < len(team_vals) - 1:
            below_val = team_vals[my_idx + 1][1]
            gap_below = round(abs(below_val - my_val), 3)

        details[fg_key] = {
            "rank": my_rank,
            "gap_to_next": gap_to_next,
            "gap_below": gap_below,
            "points_available": points_available,
        }

    return details


async def load_league_projections(
    db: AsyncSession,
    league_id: int,
) -> tuple[list[dict], dict[str, dict[str, float]], str, dict, dict[int, Any]]:
    """Load and project all teams for a league.

    Returns (categories, all_team_totals, my_team_key, my_rate_accum, players_by_id)
    """
    # Get league
    league_result = await db.execute(
        select(UserLeague).where(UserLeague.id == league_id)
    )
    league = league_result.scalar_one_or_none()
    if not league:
        raise ValueError(f"League {league_id} not found")

    # Parse scoring categories
    categories = parse_scoring_categories(league.scoring_categories)
    if not categories:
        raise ValueError(f"No valid scoring categories for league {league_id}")

    # Load all rosters
    roster_result = await db.execute(
        select(LeagueRoster).where(
            LeagueRoster.league_id == league_id,
            LeagueRoster.player_id.isnot(None),
        )
    )
    rosters = roster_result.scalars().all()

    # Find user's team key
    team_result = await db.execute(
        select(LeagueTeam).where(
            LeagueTeam.league_id == league_id,
            LeagueTeam.is_current_user == 1,
        )
    )
    my_team = team_result.scalar_one_or_none()
    my_team_key = my_team.yahoo_team_key if my_team else ""

    # Collect all player IDs
    all_player_ids = [r.player_id for r in rosters if r.player_id]

    # Load player info
    if all_player_ids:
        player_result = await db.execute(
            select(Player).where(Player.id.in_(all_player_ids))
        )
        players_by_id = {p.id: p for p in player_result.scalars().all()}
    else:
        players_by_id = {}

    # Load projections — keyed as {player_id: {stat_type: stats_dict}}
    # This supports two-way players who have both batting and pitching projections
    projections: dict[int, dict[str, dict]] = {}
    if all_player_ids:
        seen: dict[tuple[int, str], bool] = {}
        for stat_type in ("projections_batting", "projections_pitching"):
            result = await db.execute(
                select(PlayerStats)
                .where(
                    PlayerStats.player_id.in_(all_player_ids),
                    PlayerStats.source == "fangraphs",
                    PlayerStats.stat_type == stat_type,
                )
                .order_by(PlayerStats.date.desc())
            )
            for stat in result.scalars().all():
                key = (stat.player_id, stat_type)
                if key not in seen:
                    seen[key] = True
                    try:
                        parsed = json.loads(stat.stats)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if stat.player_id not in projections:
                        projections[stat.player_id] = {}
                    projections[stat.player_id][stat_type] = parsed

    # Project all teams
    all_team_totals = project_all_teams(rosters, players_by_id, projections, categories)

    # Build rate accumulator for user's team (needed for player scoring)
    my_rate_accum: dict[str, tuple[float, float]] = {}
    my_player_ids = [r.player_id for r in rosters if r.yahoo_team_key == my_team_key]
    for pid in my_player_ids:
        player_projs = projections.get(pid)
        if not player_projs:
            continue
        for cat in categories:
            fg_key = cat["fg_key"]
            if not cat["is_rate"]:
                continue
            cat_is_pitching = cat["position_type"] == "P"
            proj = player_projs.get("projections_pitching" if cat_is_pitching else "projections_batting", {})
            if not proj:
                continue
            val = _get_num(proj, fg_key, fg_key.lower())
            weight_key = "IP" if cat_is_pitching else "PA"
            weight = _get_num(proj, weight_key, weight_key.lower()) or 0
            if val is not None and weight > 0:
                prev = my_rate_accum.get(fg_key, (0.0, 0.0))
                my_rate_accum[fg_key] = (prev[0] + val * weight, prev[1] + weight)

    return categories, all_team_totals, my_team_key, my_rate_accum, players_by_id


async def get_team_analysis(db: AsyncSession, league_id: int) -> dict:
    """Full team analysis response for the API."""
    league_result = await db.execute(
        select(UserLeague).where(UserLeague.id == league_id)
    )
    league = league_result.scalar_one_or_none()
    if not league:
        return {"error": "League not found"}

    try:
        categories, all_team_totals, my_team_key, _, _ = await load_league_projections(
            db, league_id
        )
    except ValueError as e:
        return {"error": str(e)}

    my_totals = all_team_totals.get(my_team_key, {})
    is_roto = league.format and league.format != "head"

    # Compute needs
    if is_roto:
        needs = compute_category_needs_roto(my_team_key, all_team_totals, categories)
        gap_details = compute_roto_gap_details(my_team_key, all_team_totals, categories)
    else:
        needs = compute_category_needs_h2h(my_totals, all_team_totals, categories)
        gap_details = {}

    # League averages
    num_teams = len(all_team_totals)
    league_avgs: dict[str, float] = {}
    for cat in categories:
        fg_key = cat["fg_key"]
        vals = [t.get(fg_key, 0) for t in all_team_totals.values()]
        league_avgs[fg_key] = sum(vals) / len(vals) if vals else 0

    # Ranks
    ranks: dict[str, int] = {}
    for cat in categories:
        fg_key = cat["fg_key"]
        vals = sorted(
            [t.get(fg_key, 0) for t in all_team_totals.values()],
            reverse=not cat["lower_is_better"],
        )
        my_val = my_totals.get(fg_key, 0)
        rank = 1
        for v in vals:
            if cat["lower_is_better"]:
                if v < my_val:
                    rank += 1
            else:
                if v > my_val:
                    rank += 1
        ranks[fg_key] = rank

    # Build category display names list
    scoring_cat_names = [c["display_name"] for c in categories]

    # Build categories array
    cat_array = []
    for cat in categories:
        fg_key = cat["fg_key"]
        entry = {
            "category": cat["display_name"],
            "my_value": round(my_totals.get(fg_key, 0), 3 if cat["is_rate"] else 1),
            "league_avg": round(league_avgs.get(fg_key, 0), 3 if cat["is_rate"] else 1),
            "rank": ranks.get(fg_key, 0),
            "need": round(needs.get(fg_key, 0), 2),
            "gap_to_next": None,
            "gap_below": None,
            "points_available": None,
        }
        if is_roto and fg_key in gap_details:
            gd = gap_details[fg_key]
            entry["rank"] = gd["rank"]
            entry["gap_to_next"] = gd["gap_to_next"]
            entry["gap_below"] = gd["gap_below"]
            entry["points_available"] = gd["points_available"]
        cat_array.append(entry)

    # Find team name
    team_result = await db.execute(
        select(LeagueTeam).where(
            LeagueTeam.league_id == league_id,
            LeagueTeam.is_current_user == 1,
        )
    )
    my_team_row = team_result.scalar_one_or_none()
    team_name = my_team_row.team_name if my_team_row else "My Team"

    return {
        "league_format": league.format or "head",
        "scoring_categories": scoring_cat_names,
        "my_team": {
            "team_name": team_name,
            "projected_totals": {
                cat["display_name"]: round(my_totals.get(cat["fg_key"], 0), 3 if cat["is_rate"] else 1)
                for cat in categories
            },
            "category_ranks": {cat["display_name"]: ranks.get(cat["fg_key"], 0) for cat in categories},
            "category_needs": {cat["display_name"]: round(needs.get(cat["fg_key"], 0), 2) for cat in categories},
        },
        "categories": cat_array,
        "num_teams": num_teams,
        "current_matchup": None,  # Populated by route for H2H
    }
```

- [ ] **Step 4: Run all tests**

```bash
cd /home/nbrown/projects/ripken && python -m pytest backend/tests/test_category_value.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/category_value.py backend/tests/test_category_value.py
git commit -m "feat: add orchestration functions and roto gap details"
```

---

## Task 6: Team Analysis API Route

**Files:**
- Create: `backend/api/routes/team_analysis.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Create the team analysis route**

```python
# backend/api/routes/team_analysis.py
"""Team analysis API route — category strengths, weaknesses, and needs."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db_session
from backend.analytics.category_value import get_team_analysis
from backend.database.models import LeagueTeam, UserLeague
from backend.yahoo.client import get_matchup

router = APIRouter(prefix="/api", tags=["team-analysis"])
logger = logging.getLogger(__name__)


@router.get("/leagues/{league_id}/team-analysis")
async def team_analysis(
    league_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    """Get category analysis for the user's team in a league."""
    result = await get_team_analysis(db, league_id)
    if "error" in result:
        return result

    # Populate current_matchup for H2H leagues
    if result.get("league_format") == "head":
        try:
            team_result = await db.execute(
                select(LeagueTeam).where(
                    LeagueTeam.league_id == league_id,
                    LeagueTeam.is_current_user == 1,
                )
            )
            my_team = team_result.scalar_one_or_none()
            if my_team:
                matchup_data = await get_matchup(db, my_team.yahoo_team_key)
                # Parse opponent from Yahoo matchup response
                # Structure varies; extract opponent team name if available
                matchups = matchup_data.get("matchups", {})
                if isinstance(matchups, dict):
                    matchup_list = matchups.get("matchup", [])
                    if isinstance(matchup_list, list) and matchup_list:
                        current = matchup_list[-1]  # most recent/current matchup
                        teams = current.get("teams", {}).get("team", [])
                        for team in teams if isinstance(teams, list) else []:
                            team_info = team[0] if isinstance(team, list) and team else team
                            if isinstance(team_info, dict):
                                name = team_info.get("name", "")
                                if name and name != my_team.team_name:
                                    result["current_matchup"] = {
                                        "opponent": name,
                                        "category_comparison": [],  # TODO: populate with projections
                                    }
        except Exception:
            logger.warning("Failed to fetch H2H matchup data", exc_info=True)

    return result
```

- [ ] **Step 2: Register the router in main.py**

Add to `backend/main.py` imports:

```python
from backend.api.routes.team_analysis import router as team_analysis_router
```

Add to router registrations (after `waivers_router`):

```python
app.include_router(team_analysis_router)
```

- [ ] **Step 3: Verify the app starts**

```bash
cd /home/nbrown/projects/ripken && timeout 5 python -m uvicorn backend.main:app --port 8099 2>&1 || true
```

Expected: App starts without import errors (will timeout after 5s, that's fine).

- [ ] **Step 4: Commit**

```bash
git add backend/api/routes/team_analysis.py backend/main.py
git commit -m "feat: add team analysis API endpoint"
```

---

## Task 7: Enhance Waivers Route with Value Scores

**Files:**
- Modify: `backend/api/routes/waivers.py`

Integrate the value engine into the existing waivers endpoint. Add `value_score` and `category_impact` to each player, change default sort to value_score.

- [ ] **Step 1: Add value scoring imports and logic to waivers route**

At the top of `backend/api/routes/waivers.py`, add:

```python
from backend.analytics.category_value import (
    load_league_projections,
    score_players,
)
```

- [ ] **Step 2: Add value scoring to the endpoint**

Inside `get_waivers()`, after the `all_proj_ids` line (line 129) and before building position groups, add the value scoring logic. Replace the function from line 55 to end with the updated version that:

1. Calls `load_league_projections()` to get categories, needs, and team totals
2. Builds a candidates dict from all players with projections
3. Calls `score_players()` to get value scores
4. Adds `value_score` and `category_impact` to each player entry
5. Changes sort to `value_score` descending

The key changes in the `get_waivers` function:

After loading projections (around line 129), add:

```python
    # Compute value scores
    value_scores: dict[int, dict] = {}
    try:
        categories, all_team_totals, my_team_key, my_rate_accum, all_players = (
            await load_league_projections(db, league_id)
        )
        is_roto = league.format and league.format != "head"
        if is_roto:
            from backend.analytics.category_value import compute_category_needs_roto
            needs = compute_category_needs_roto(my_team_key, all_team_totals, categories)
        else:
            from backend.analytics.category_value import compute_category_needs_h2h
            my_totals = all_team_totals.get(my_team_key, {})
            needs = compute_category_needs_h2h(my_totals, all_team_totals, categories)

        # Build candidate projections — two-dict format for two-way players
        candidate_projs: dict[int, dict[str, dict]] = {}
        for pid in all_proj_ids:
            projs: dict[str, dict] = {}
            if pid in batting_proj:
                try:
                    projs["projections_batting"] = json.loads(batting_proj[pid])
                except (json.JSONDecodeError, TypeError):
                    pass
            if pid in pitching_proj:
                try:
                    projs["projections_pitching"] = json.loads(pitching_proj[pid])
                except (json.JSONDecodeError, TypeError):
                    pass
            if projs:
                candidate_projs[pid] = projs

        value_scores = score_players(
            candidate_projs, players_by_id, needs, categories,
            all_team_totals.get(my_team_key, {}), my_rate_accum,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Value scoring failed, falling back")
```

Update the `entry` dict to include value data:

```python
        score_data = value_scores.get(pid, {})
        entry = {
            "player_id": pid,
            "full_name": player.full_name,
            "team": player.team,
            "status": player.status or "active",
            "owner": ownership["team_name"] if ownership else None,
            "is_mine": ownership["is_mine"] if ownership else False,
            "is_available": ownership is None,
            "projection": proj,
            "value_score": score_data.get("value_score"),
            "category_impact": score_data.get("category_impact"),
        }
```

Update the sort function to use value_score:

```python
def _sort_key(player: dict, is_pitcher: bool) -> float:
    """Sort by value_score first, then Off/WAR as fallback."""
    vs = player.get("value_score")
    if vs is not None:
        return -vs
    proj = player.get("projection") or {}
    if is_pitcher:
        return -(proj.get("WAR") or 0)
    return -(proj.get("Off") or 0)
```

- [ ] **Step 3: Also return category_needs in the waivers response**

Add `category_needs` to the response dict so the frontend can render the needs panel:

```python
    # Build needs summary for the frontend panel
    needs_summary = []
    if value_scores:  # means scoring succeeded
        for cat in categories:
            fg_key = cat["fg_key"]
            needs_summary.append({
                "category": cat["display_name"],
                "need": round(needs.get(fg_key, 0), 2),
                "rank": None,  # could add ranks here if needed
            })
        needs_summary.sort(key=lambda x: -x["need"])

    return {
        "league_id": league_id,
        "league_name": league.league_name,
        "positions": ordered,
        "category_needs": needs_summary,
    }
```

- [ ] **Step 4: Verify the app still starts**

```bash
cd /home/nbrown/projects/ripken && timeout 5 python -m uvicorn backend.main:app --port 8099 2>&1 || true
```

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/waivers.py
git commit -m "feat: add value scores and category needs to waivers endpoint"
```

---

## Task 8: Frontend Types

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Add TeamAnalysis and enhanced Waivers types**

Add to `frontend/src/lib/api.ts`:

```typescript
// --- Team Analysis types ---

export interface CategoryDetail {
  category: string;
  my_value: number;
  league_avg: number;
  rank: number;
  need: number;
  gap_to_next: number | null;
  gap_below: number | null;
  points_available: number | null;
}

export interface TeamAnalysisResponse {
  league_format: string;
  scoring_categories: string[];
  my_team: {
    team_name: string;
    projected_totals: Record<string, number>;
    category_ranks: Record<string, number>;
    category_needs: Record<string, number>;
  };
  categories: CategoryDetail[];
  num_teams: number;
  current_matchup: {
    opponent: string;
    category_comparison: {
      category: string;
      my_projected: number;
      opp_projected: number;
      edge: string;
    }[];
  } | null;
  error?: string;
}

export interface CategoryNeedSummary {
  category: string;
  need: number;
  rank: number | null;
}

export interface CategoryImpact {
  projected: number;
  impact: number;
  need: number;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: add TeamAnalysis and value scoring frontend types"
```

---

## Task 9: Team Analysis Page

**Files:**
- Create: `frontend/src/app/team-analysis/page.tsx`

Build the dedicated Team Analysis page with radar chart and category detail table.

- [ ] **Step 1: Create the Team Analysis page**

Create `frontend/src/app/team-analysis/page.tsx`. Follow the same patterns as `frontend/src/app/waivers/page.tsx` — same header/nav, `fetchApi` pattern, Tailwind styling.

Key components to implement in this file:

**RadarChart component** — SVG-based, no external library:

```typescript
// Radar chart geometry helpers
function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function RadarChart({ categories, numTeams }: { categories: CategoryDetail[]; numTeams: number }) {
  const size = 300;
  const cx = size / 2;
  const cy = size / 2;
  const maxR = size / 2 - 40; // leave room for labels
  const n = categories.length;
  if (n < 3) return null;

  const angleStep = 360 / n;

  // Normalize each category to 0-1 (percentile-based: rank/numTeams inverted)
  // Rank 1 = best = 1.0 (outer edge), rank N = worst = near center
  const myNorm = categories.map((c) => 1 - (c.rank - 1) / Math.max(numTeams - 1, 1));
  const avgNorm = categories.map(() => 0.5); // league average = 50th percentile

  const toPoints = (values: number[]) =>
    values
      .map((v, i) => {
        const { x, y } = polarToCartesian(cx, cy, v * maxR, i * angleStep);
        return `${x},${y}`;
      })
      .join(" ");

  // Background rings at 25%, 50%, 75%, 100%
  const rings = [0.25, 0.5, 0.75, 1.0];

  // Need-based label colors
  const needColor = (need: number) => {
    if (need >= 0.7) return "#ef4444"; // red
    if (need >= 0.4) return "#eab308"; // yellow
    return "#22c55e"; // green
  };

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="mx-auto">
      {/* Background rings */}
      {rings.map((r) => (
        <polygon
          key={r}
          points={Array.from({ length: n }, (_, i) => {
            const { x, y } = polarToCartesian(cx, cy, r * maxR, i * angleStep);
            return `${x},${y}`;
          }).join(" ")}
          fill="none"
          stroke="currentColor"
          strokeWidth="0.5"
          className="text-zinc-700"
        />
      ))}
      {/* Axes */}
      {categories.map((_, i) => {
        const { x, y } = polarToCartesian(cx, cy, maxR, i * angleStep);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="currentColor" strokeWidth="0.5" className="text-zinc-700" />;
      })}
      {/* League average shape (dashed) */}
      <polygon points={toPoints(avgNorm)} fill="none" stroke="#666" strokeWidth="1" strokeDasharray="4,3" />
      {/* My team shape */}
      <polygon points={toPoints(myNorm)} fill="rgba(78,205,196,0.2)" stroke="#4ecdc4" strokeWidth="2" />
      {/* Labels */}
      {categories.map((cat, i) => {
        const { x, y } = polarToCartesian(cx, cy, maxR + 22, i * angleStep);
        return (
          <text key={cat.category} x={x} y={y} textAnchor="middle" dominantBaseline="middle" fontSize="10" fill={needColor(cat.need)}>
            {cat.category} ({cat.rank})
          </text>
        );
      })}
    </svg>
  );
}
```

**Summary cards:**
```typescript
function SummaryCards({ categories }: { categories: CategoryDetail[] }) {
  const sorted = [...categories].sort((a, b) => b.need - a.need);
  const biggestNeed = sorted[0];
  const biggestStrength = sorted[sorted.length - 1];

  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4">
        <div className="text-xs text-zinc-400 uppercase">Biggest Need</div>
        <div className="text-2xl font-bold text-red-400">{biggestNeed?.category}</div>
        <div className="text-xs text-zinc-500">Rank: {biggestNeed?.rank}th</div>
      </div>
      <div className="rounded-lg bg-green-500/10 border border-green-500/20 p-4">
        <div className="text-xs text-zinc-400 uppercase">Biggest Strength</div>
        <div className="text-2xl font-bold text-green-400">{biggestStrength?.category}</div>
        <div className="text-xs text-zinc-500">Rank: {biggestStrength?.rank}th</div>
      </div>
      <div className="rounded-lg bg-zinc-800 border border-zinc-700 p-4">
        <div className="text-xs text-zinc-400 uppercase">Categories</div>
        <div className="text-2xl font-bold">{categories.length}</div>
        <div className="text-xs text-zinc-500">Scoring categories</div>
      </div>
    </div>
  );
}
```

**Page structure** — use the same `fetchApi<TeamAnalysisResponse>` pattern, league selector, loading/error states as `waivers/page.tsx`. Render:
1. SummaryCards
2. RadarChart
3. Category detail table — conditionally render Gap/Points columns when `league_format !== "head"` (roto)
4. H2H matchup panel (if `current_matchup` is not null): show opponent name and category comparison

Import `TeamAnalysisResponse` and `CategoryDetail` from `@/lib/api`.

- [ ] **Step 2: Verify it renders**

```bash
cd /home/nbrown/projects/ripken/frontend && npm run build 2>&1 | tail -5
```

Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/team-analysis/page.tsx
git commit -m "feat: add Team Analysis page with radar chart and category table"
```

---

## Task 10: Waivers Page — Needs Panel and Value Score

**Files:**
- Modify: `frontend/src/app/waivers/page.tsx`

Add the collapsible needs panel and value score column to the existing waivers page.

- [ ] **Step 1: Update WaiverPlayer and WaiversResponse types**

In `frontend/src/app/waivers/page.tsx`, update the interfaces:

```typescript
interface WaiverPlayer {
  player_id: number;
  full_name: string;
  team: string | null;
  status: string;
  owner: string | null;
  is_mine: boolean;
  is_available: boolean;
  projection: Record<string, number> | null;
  value_score: number | null;
  category_impact: Record<string, { projected: number; impact: number; need: number }> | null;
}

interface WaiversResponse {
  league_id: number;
  league_name: string;
  positions: Record<string, WaiverPlayer[]>;
  category_needs: { category: string; need: number; rank: number | null }[];
}
```

- [ ] **Step 2: Add the collapsible needs panel component**

Add a `CategoryNeedsPanel` component before the `PositionTable` component:

```typescript
function CategoryNeedsPanel({
  needs,
  collapsed,
  onToggle,
}: {
  needs: { category: string; need: number; rank: number | null }[];
  collapsed: boolean;
  onToggle: () => void;
}) {
  if (!needs || needs.length === 0) return null;

  const needLevel = (n: number) => {
    if (n >= 0.7) return { label: "High", color: "bg-red-500/15 border-red-500/30 text-red-400" };
    if (n >= 0.4) return { label: "Med", color: "bg-yellow-500/12 border-yellow-500/25 text-yellow-400" };
    return { label: "Low", color: "bg-green-500/10 border-green-500/20 text-green-400" };
  };

  return (
    <div className="mb-6 rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold">Your Category Needs</span>
        <button onClick={onToggle} className="text-xs text-zinc-400 hover:text-zinc-300">
          {collapsed ? "▶ Expand" : "▼ Collapse"}
        </button>
      </div>
      {!collapsed && (
        <>
          <div className="flex flex-wrap gap-2">
            {needs.map((n) => {
              const level = needLevel(n.need);
              return (
                <div
                  key={n.category}
                  className={`rounded-md border px-3 py-1.5 text-center ${level.color}`}
                >
                  <div className="text-sm font-bold">{n.category}</div>
                  <div className="text-[10px]">Need: {level.label}</div>
                </div>
              );
            })}
          </div>
          <div className="mt-2 text-right">
            <Link href="/team-analysis" className="text-xs text-cyan-400 hover:text-cyan-300">
              View full analysis →
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Add value score column to PositionTable**

Update `PositionTable` to:
1. Add "Value" as the first column header
2. Show color-coded value score for each player
3. Track expanded rows for category impact breakdown
4. Render the breakdown below expanded rows

Add value score color helper:

```typescript
function valueColor(score: number | null): string {
  if (score == null) return "text-zinc-500";
  if (score >= 70) return "text-green-400";
  if (score >= 40) return "text-yellow-400";
  return "text-zinc-500";
}
```

- [ ] **Step 4: Add needs panel state and rendering to the page**

In the `WaiversPage` component, add:

```typescript
const [needsCollapsed, setNeedsCollapsed] = useState(false);
```

Render the panel before the position tables:

```tsx
{!loading && data && data.category_needs && (
  <CategoryNeedsPanel
    needs={data.category_needs}
    collapsed={needsCollapsed}
    onToggle={() => setNeedsCollapsed(!needsCollapsed)}
  />
)}
```

- [ ] **Step 5: Add "Team Analysis" to the nav bar**

Add to the nav in the header (and in the team analysis page header too):

```tsx
<Link href="/team-analysis" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Team Analysis</Link>
```

- [ ] **Step 6: Verify it builds**

```bash
cd /home/nbrown/projects/ripken/frontend && npm run build 2>&1 | tail -5
```

Expected: Build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/waivers/page.tsx
git commit -m "feat: add needs panel, value scores, and expandable breakdown to waivers page"
```

---

## Task 11: Navigation Update

**Files:**
- Modify: All pages with nav bar (waivers, roster, league, bullpen, lineups, pitching, matchup, prospects, dashboard)

- [ ] **Step 1: Add "Team Analysis" link to all page nav bars**

Every page currently has a hardcoded nav bar in its header. Add a "Team Analysis" link to each one, between "Waivers" and "Bullpen":

```tsx
<Link href="/team-analysis" className="text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">Analysis</Link>
```

Use "Analysis" as the short label to keep the nav bar compact.

Pages to update:
- `frontend/src/app/page.tsx` (dashboard)
- `frontend/src/app/roster/page.tsx`
- `frontend/src/app/league/page.tsx`
- `frontend/src/app/bullpen/page.tsx`
- `frontend/src/app/lineups/page.tsx`
- `frontend/src/app/pitching/page.tsx`
- `frontend/src/app/matchup/page.tsx`
- `frontend/src/app/prospects/page.tsx`

- [ ] **Step 2: Verify build**

```bash
cd /home/nbrown/projects/ripken/frontend && npm run build 2>&1 | tail -5
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/
git commit -m "feat: add Team Analysis link to all page nav bars"
```

---

## Task 12: End-to-End Verification

- [ ] **Step 1: Run all backend tests**

```bash
cd /home/nbrown/projects/ripken && python -m pytest backend/tests/ -v
```

Expected: All pass.

- [ ] **Step 2: Run lint**

```bash
cd /home/nbrown/projects/ripken && make lint
```

Expected: Clean.

- [ ] **Step 3: Verify frontend builds**

```bash
cd /home/nbrown/projects/ripken/frontend && npm run build
```

Expected: Success.

- [ ] **Step 4: Manual smoke test**

Start dev servers and verify:
1. `/team-analysis` page loads, shows radar chart and category table
2. Switching leagues shows different data
3. `/waivers` page shows needs panel at top
4. Value score column appears and players are sorted by it
5. Clicking a player row expands to show category impact

```bash
cd /home/nbrown/projects/ripken && make dev
```

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A && git commit -m "fix: address issues found during end-to-end testing"
```
