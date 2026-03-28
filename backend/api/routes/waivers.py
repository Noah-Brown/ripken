"""Waiver wire API routes — position-grouped with projections."""

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.category_value import (
    compute_category_needs_h2h,
    compute_category_needs_roto,
    load_league_projections,
    score_players,
)
from backend.api.dependencies import get_db_session
from backend.database.models import (
    LeagueRoster,
    LeagueTeam,
    Player,
    PlayerStats,
    UserLeague,
)

router = APIRouter(prefix="/api", tags=["waivers"])

PITCHER_POSITIONS = {"SP", "RP", "P"}

BATTER_KEYS = ["PA", "R", "HR", "RBI", "SB", "AVG", "OBP", "SLG", "OPS", "wRC+", "Off"]
PITCHER_KEYS = ["IP", "W", "QS", "SV", "ERA", "WHIP", "K/9", "SO", "WAR"]

POSITION_ORDER = [
    "C", "1B", "2B", "SS", "3B", "OF", "Util", "DH",
    "CI", "MI", "SP", "RP", "P", "BN", "IL", "IL+", "NA",
]


def _extract_projection(stats_json: str | None, keys: list[str]) -> dict | None:
    """Parse a stats JSON blob and extract only the requested keys."""
    if not stats_json:
        return None
    try:
        raw = json.loads(stats_json)
    except (json.JSONDecodeError, TypeError):
        return None
    proj = {}
    for k in keys:
        v = raw.get(k)
        if v is not None:
            proj[k] = v
    return proj if proj else None


def _sort_key(player: dict, is_pitcher: bool) -> float:
    """Sort by value_score first, then Off/WAR as fallback."""
    vs = player.get("value_score")
    if vs is not None:
        return -vs
    proj = player.get("projection") or {}
    if is_pitcher:
        return -(proj.get("WAR") or 0)
    return -(proj.get("Off") or 0)


@router.get("/waivers/{league_id}")
async def get_waivers(
    league_id: int,
    position: str | None = Query(None, description="Filter by position"),
    db: AsyncSession = Depends(get_db_session),
):
    """All players with projections, grouped by position, with ownership."""
    # Verify league
    league_result = await db.execute(
        select(UserLeague).where(UserLeague.id == league_id)
    )
    league = league_result.scalar_one_or_none()
    if not league:
        return {"league_id": league_id, "error": "League not found", "positions": {}}

    # User's team keys
    team_result = await db.execute(
        select(LeagueTeam.yahoo_team_key).where(
            LeagueTeam.league_id == league_id,
            LeagueTeam.is_current_user == 1,
        )
    )
    user_team_keys = {row[0] for row in team_result.all()}

    # Ownership map: player_id -> {team_name, is_mine, roster_position}
    ownership_result = await db.execute(
        select(
            LeagueRoster.player_id,
            LeagueRoster.yahoo_team_name,
            LeagueRoster.yahoo_team_key,
            LeagueRoster.roster_position,
        ).where(
            LeagueRoster.league_id == league_id,
            LeagueRoster.player_id.isnot(None),
        )
    )
    ownership_map: dict[int, dict] = {}
    for row in ownership_result.all():
        if row.player_id is not None:
            ownership_map[row.player_id] = {
                "team_name": row.yahoo_team_name,
                "is_mine": row.yahoo_team_key in user_team_keys,
                "roster_position": row.roster_position,
            }

    # Load batting projections (most recent date per player)
    batting_proj: dict[int, str] = {}
    batting_result = await db.execute(
        select(PlayerStats.player_id, PlayerStats.stats)
        .where(
            PlayerStats.source == "fangraphs",
            PlayerStats.stat_type == "projections_batting",
        )
        .order_by(PlayerStats.date.desc())
    )
    for row in batting_result.all():
        if row.player_id not in batting_proj:
            batting_proj[row.player_id] = row.stats

    # Load pitching projections
    pitching_proj: dict[int, str] = {}
    pitching_result = await db.execute(
        select(PlayerStats.player_id, PlayerStats.stats)
        .where(
            PlayerStats.source == "fangraphs",
            PlayerStats.stat_type == "projections_pitching",
        )
        .order_by(PlayerStats.date.desc())
    )
    for row in pitching_result.all():
        if row.player_id not in pitching_proj:
            pitching_proj[row.player_id] = row.stats

    # All player IDs with projections
    all_proj_ids = set(batting_proj.keys()) | set(pitching_proj.keys())

    # Load player info
    player_result = await db.execute(
        select(Player).where(Player.id.in_(all_proj_ids))
    )
    players_by_id = {p.id: p for p in player_result.scalars().all()}

    # Compute value scores
    value_scores: dict[int, dict] = {}
    needs: dict = {}
    categories: list = []
    try:
        categories, all_team_totals, my_team_key, my_rate_accum, all_players = (
            await load_league_projections(db, league_id)
        )
        is_roto = league.format and league.format != "head"
        if is_roto:
            needs = compute_category_needs_roto(my_team_key, all_team_totals, categories)
        else:
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

    # Build position groups
    positions: dict[str, list] = {}

    for pid in all_proj_ids:
        player = players_by_id.get(pid)
        if not player:
            continue

        ownership = ownership_map.get(pid)
        is_pitcher = player.position in PITCHER_POSITIONS if player.position else False

        # Determine position for grouping
        if ownership:
            pos = ownership["roster_position"] or player.position or "BN"
        else:
            pos = player.position or "Util"

        # Filter by position if requested
        if position and pos != position and player.position != position:
            continue

        # Get projection
        if is_pitcher:
            proj = _extract_projection(pitching_proj.get(pid), PITCHER_KEYS)
        else:
            proj = _extract_projection(batting_proj.get(pid), BATTER_KEYS)

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

        if pos not in positions:
            positions[pos] = []
        positions[pos].append(entry)

    # Sort within each position group
    for pos, players_list in positions.items():
        is_pitcher_pos = pos in PITCHER_POSITIONS
        players_list.sort(key=lambda p: _sort_key(p, is_pitcher_pos))

    # Order position groups
    ordered: dict[str, list] = {}
    for pos in POSITION_ORDER:
        if pos in positions:
            ordered[pos] = positions[pos]
    for pos in positions:
        if pos not in ordered:
            ordered[pos] = positions[pos]

    # Build needs summary for the frontend panel
    needs_summary = []
    if value_scores:
        for cat in categories:
            fg_key = cat["fg_key"]
            needs_summary.append({
                "category": cat["display_name"],
                "need": round(needs.get(fg_key, 0), 2),
                "rank": None,
            })
        needs_summary.sort(key=lambda x: -x["need"])

    return {
        "league_id": league_id,
        "league_name": league.league_name,
        "positions": ordered,
        "category_needs": needs_summary,
    }
