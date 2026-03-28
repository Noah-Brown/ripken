"""Category value engine — scores players by team need.

Three layers:
1. Team Projection: sum FanGraphs ROS projections per roster
2. Category Needs: identify weak categories (H2H median / roto gap-aware)
3. Player Value: score candidates 0-100 by weighted category impact
"""

import json
import logging
import statistics
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

STAT_MAPPING: dict[str, str | None] = {
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


# ---------------------------------------------------------------------------
# Layer 1: Team Projection
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Layer 2: Category Need Assessment
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Layer 3: Player Value Scoring
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Orchestration — Full Pipeline Functions
# ---------------------------------------------------------------------------

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
