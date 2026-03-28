"""Tests for category value engine."""

import json
import pytest
from unittest.mock import MagicMock

from backend.analytics.category_value import (
    LOWER_IS_BETTER,
    PITCHING_STATS,
    RATE_STATS,
    STAT_MAPPING,
    parse_scoring_categories,
    project_all_teams,
    compute_category_needs_h2h,
    compute_category_needs_roto,
    score_players,
    compute_roto_gap_details,
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


# ---------------------------------------------------------------------------
# Helpers for tests
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Task 1: Stat Mapping and Category Parsing
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Task 2: Team Projection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Task 3: Category Need Assessment
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Task 4: Player Value Scoring
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Task 5: Roto Gap Details
# ---------------------------------------------------------------------------

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
