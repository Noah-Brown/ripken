"""Start/sit confidence scoring for hitters.

Gives each hitter on the user's roster a confidence score for today's game
based on opposing pitcher, platoon splits, park factor, and recent performance.
"""

import json
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import (
    Game,
    Player,
    PlayerStats,
    ProbablePitcher,
)

logger = logging.getLogger(__name__)

# Pitching positions — these players don't get start/sit scores
PITCHER_POSITIONS = {"SP", "RP", "P"}


async def compute_start_sit_scores(
    db: AsyncSession,
    player_ids: list[int],
) -> dict[int, dict]:
    """Compute start/sit confidence for a list of hitter player IDs.

    Returns a dict mapping player_id to:
        {score: int, label: str, factors: dict}
    """
    today = date.today().isoformat()

    # Load today's games and build team -> game+opponent mapping
    games_result = await db.execute(select(Game).where(Game.date == today))
    games = games_result.scalars().all()

    team_game_map: dict[str, Game] = {}
    team_opponent_map: dict[str, str] = {}
    for game in games:
        team_game_map[game.home_team] = game
        team_game_map[game.away_team] = game
        team_opponent_map[game.home_team] = game.away_team
        team_opponent_map[game.away_team] = game.home_team

    # Load probable pitchers for today, keyed by team they're pitching FOR
    pp_result = await db.execute(
        select(ProbablePitcher, Player)
        .join(Player, ProbablePitcher.player_id == Player.id)
        .join(Game, ProbablePitcher.game_id == Game.id)
        .where(Game.date == today)
    )
    pitchers_by_team: dict[str, Player] = {}
    for pp, pitcher in pp_result.all():
        pitchers_by_team[pp.team] = pitcher

    # Load players
    players_result = await db.execute(
        select(Player).where(Player.id.in_(player_ids))
    )
    players = {p.id: p for p in players_result.scalars().all()}

    # Batch-load FanGraphs stats for these players
    fg_stats = await _load_fg_stats(db, player_ids)

    # Load FanGraphs stats for opposing pitchers too
    opp_pitcher_ids = [p.id for p in pitchers_by_team.values()]
    if opp_pitcher_ids:
        pitcher_fg = await _load_fg_stats(db, opp_pitcher_ids)
    else:
        pitcher_fg = {}

    results: dict[int, dict] = {}

    for pid in player_ids:
        player = players.get(pid)
        if not player or not player.team:
            continue

        # Skip pitchers
        if player.position in PITCHER_POSITIONS:
            continue

        # Not playing today
        game = team_game_map.get(player.team)
        if not game:
            results[pid] = {
                "score": None,
                "label": "Off Day",
                "factors": {},
            }
            continue

        # Find opposing pitcher
        opponent_team = team_opponent_map.get(player.team, "")
        opposing_pitcher = pitchers_by_team.get(opponent_team)

        # Compute factors
        factors = {}

        # 1. Platoon advantage (30%)
        platoon_score = _compute_platoon_advantage(player, opposing_pitcher)
        factors["platoon"] = round(platoon_score, 1)

        # 2. Opposing pitcher weakness (25%)
        pitcher_weakness = _compute_pitcher_weakness(opposing_pitcher, pitcher_fg)
        factors["pitcher_weakness"] = round(pitcher_weakness, 1)

        # 3. Park factor (20%)
        park_score = _compute_park_factor(game)
        factors["park_factor"] = round(park_score, 1)

        # 4. Recent hot/cold (15%)
        player_stats = fg_stats.get(pid, {})
        recent_score = _compute_recent_form(player_stats)
        factors["recent_form"] = round(recent_score, 1)

        # 5. Season baseline (10%)
        baseline = _compute_season_baseline(player_stats)
        factors["season_baseline"] = round(baseline, 1)

        # Weighted composite
        raw_score = (
            0.30 * platoon_score
            + 0.25 * pitcher_weakness
            + 0.20 * park_score
            + 0.15 * recent_score
            + 0.10 * baseline
        )

        # Normalize to 0-100
        score = max(0, min(100, int(raw_score)))
        label = _score_to_label(score)

        results[pid] = {
            "score": score,
            "label": label,
            "factors": factors,
        }

    return results


def _compute_platoon_advantage(player: Player, opposing_pitcher: Player | None) -> float:
    """Compute platoon advantage factor (0-100).

    Hitters generally hit better against opposite-hand pitchers.
    """
    if not opposing_pitcher or not opposing_pitcher.throws or not player.bats:
        return 50.0  # Neutral if unknown

    bats = player.bats.upper()
    throws = opposing_pitcher.throws.upper()

    # Switch hitters have slight advantage against everyone
    if bats == "S":
        return 60.0

    # Opposite hand = advantage
    if (bats == "R" and throws == "L") or (bats == "L" and throws == "R"):
        return 70.0

    # Same hand = disadvantage
    return 35.0


def _compute_pitcher_weakness(
    pitcher: Player | None,
    pitcher_fg: dict[int, dict],
) -> float:
    """Compute opposing pitcher weakness (0-100).

    A bad opposing pitcher means higher score for the hitter.
    """
    if not pitcher:
        return 60.0  # No pitcher known = slight advantage (likely bullpen game)

    stats = pitcher_fg.get(pitcher.id, {})
    if not stats:
        return 50.0

    score = 50.0

    # ERA — higher ERA = weaker pitcher = better for hitter
    era = _get_num(stats, "ERA", "era")
    if era is not None:
        if era > 5.0:
            score += 25
        elif era > 4.5:
            score += 15
        elif era > 4.0:
            score += 5
        elif era < 3.0:
            score -= 20
        elif era < 3.5:
            score -= 10

    # WHIP — higher = weaker
    whip = _get_num(stats, "WHIP", "whip")
    if whip is not None:
        if whip > 1.40:
            score += 15
        elif whip > 1.30:
            score += 5
        elif whip < 1.00:
            score -= 15
        elif whip < 1.15:
            score -= 5

    return max(0, min(100, score))


def _compute_park_factor(game: Game) -> float:
    """Compute park factor score (0-100).

    Higher park factor = more runs = better for hitters.
    """
    pf = game.park_factor_r
    if pf is None:
        return 50.0  # Neutral

    # Park factor of 1.0 is average. Scale around that.
    # Coors (~1.35) should score high, Oracle (~0.85) should score low.
    return max(0, min(100, 50 + (pf - 1.0) * 200))


def _compute_recent_form(stats: dict) -> float:
    """Score based on recent performance vs season baseline.

    Looks for hot/cold streaks in FanGraphs data.
    """
    if not stats:
        return 50.0

    # wRC+ is the best single metric
    wrc = _get_num(stats, "wRC+", "wrc_plus")
    if wrc is not None:
        if wrc > 150:
            return 85.0
        if wrc > 130:
            return 70.0
        if wrc > 110:
            return 60.0
        if wrc > 90:
            return 45.0
        if wrc > 70:
            return 30.0
        return 15.0

    # Fallback to OPS
    ops = _get_num(stats, "OPS", "ops")
    if ops is not None:
        if ops > 0.900:
            return 80.0
        if ops > 0.750:
            return 60.0
        if ops > 0.650:
            return 40.0
        return 25.0

    return 50.0


def _compute_season_baseline(stats: dict) -> float:
    """Score based on overall season quality."""
    if not stats:
        return 50.0

    wrc = _get_num(stats, "wRC+", "wrc_plus")
    if wrc is not None:
        # 100 wRC+ is league average
        return max(0, min(100, wrc))

    return 50.0


def _score_to_label(score: int) -> str:
    """Convert numeric score to a human-readable label."""
    if score > 70:
        return "Strong Start"
    if score > 50:
        return "Start"
    if score > 30:
        return "Sit if possible"
    return "Bench"


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


async def _load_fg_stats(
    db: AsyncSession, player_ids: list[int]
) -> dict[int, dict]:
    """Load the latest FanGraphs stats for a batch of players."""
    if not player_ids:
        return {}

    result = await db.execute(
        select(PlayerStats)
        .where(
            PlayerStats.player_id.in_(player_ids),
            PlayerStats.source == "fangraphs",
            PlayerStats.stat_type.in_(["batting", "pitching"]),
        )
        .order_by(PlayerStats.date.desc())
    )

    stats: dict[int, dict] = {}
    for stat in result.scalars().all():
        if stat.player_id not in stats:
            try:
                stats[stat.player_id] = json.loads(stat.stats)
            except (json.JSONDecodeError, TypeError):
                pass
    return stats
