"""Prospect call-up likelihood scoring.

Scores watched prospects on how likely they are to be called up soon
based on performance, roster need, proximity, 40-man status, service time,
and media buzz (news reports suggesting an imminent call-up).
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import Player, Prospect, ProspectBuzz, Transaction

logger = logging.getLogger(__name__)

# Level proximity scores
LEVEL_SCORES = {
    "AAA": 80,
    "AA": 50,
    "A+": 25,
    "A": 15,
    "A-": 10,
    "R": 5,
    "Rk": 5,
    "DSL": 0,
    "FCL": 0,
}


async def compute_prospect_signals(db: AsyncSession) -> list[dict]:
    """Score all watched prospects on call-up likelihood.

    Returns a list of scored prospects, sorted by signal score descending.
    """
    # Load all prospects with their player data
    result = await db.execute(
        select(Prospect, Player)
        .join(Player, Prospect.player_id == Player.id)
        .order_by(Prospect.user_rank.nulls_last(), Prospect.fangraphs_rank.nulls_last())
    )
    prospect_rows = result.all()

    if not prospect_rows:
        return []

    # Load recent transactions for context
    recent_txns = await _load_recent_callups(db)
    callup_orgs = {t["to_team"] for t in recent_txns if t.get("to_team")}

    # Load recent buzz counts per player for scoring
    buzz_counts = await _load_buzz_counts(db)
    # Load recent buzz items per player for display
    buzz_items = await _load_recent_buzz(db)

    scored = []
    for prospect, player in prospect_rows:
        # 1. Performance score (25%)
        performance = _score_performance(prospect)

        # 2. Roster need score (20%)
        roster_need = _score_roster_need(prospect, player)

        # 3. Proximity score (15%)
        proximity = _score_proximity(prospect)

        # 4. 40-man status (15%)
        forty_man = _score_forty_man(prospect)

        # 5. Service time factor (10%)
        service_time = _score_service_time()

        # 6. Media buzz factor (15%)
        buzz = _score_buzz(buzz_counts.get(player.id, 0))

        # Weighted composite
        raw_score = (
            0.25 * performance
            + 0.20 * roster_need
            + 0.15 * proximity
            + 0.15 * forty_man
            + 0.10 * service_time
            + 0.15 * buzz
        )
        signal_score = max(0, min(100, int(raw_score)))

        # Signal color
        if signal_score >= 70:
            signal = "hot"
        elif signal_score >= 40:
            signal = "warm"
        else:
            signal = "cold"

        minor_league_stats = None
        if prospect.minor_league_stats:
            try:
                minor_league_stats = json.loads(prospect.minor_league_stats)
            except (json.JSONDecodeError, TypeError):
                pass

        player_buzz = buzz_items.get(player.id, [])

        scored.append({
            "prospect_id": prospect.id,
            "player_id": player.id,
            "full_name": player.full_name,
            "org": prospect.org,
            "level": prospect.level,
            "position": player.position,
            "user_rank": prospect.user_rank,
            "fangraphs_rank": prospect.fangraphs_rank,
            "eta": prospect.eta,
            "on_40_man": bool(prospect.on_40_man),
            "scouting_notes": prospect.scouting_notes,
            "fv": prospect.fv,
            "scouting_report": prospect.scouting_report,
            "video_url": prospect.video_url,
            "trend": prospect.trend,
            "redraft_rank": prospect.redraft_rank,
            "age": prospect.age,
            "height": prospect.height,
            "weight": prospect.weight,
            "bats": player.bats,
            "throws": player.throws,
            "minor_league_stats": minor_league_stats,
            "signal_score": signal_score,
            "signal": signal,
            "factors": {
                "performance": round(performance, 1),
                "roster_need": round(roster_need, 1),
                "proximity": round(proximity, 1),
                "forty_man": round(forty_man, 1),
                "service_time": round(service_time, 1),
                "buzz": round(buzz, 1),
            },
            "buzz": player_buzz,
        })

    scored.sort(key=lambda x: x["signal_score"], reverse=True)
    return scored


def _score_performance(prospect: Prospect) -> float:
    """Score based on minor league performance."""
    if not prospect.minor_league_stats:
        return 50.0  # Neutral if no stats available

    try:
        stats = json.loads(prospect.minor_league_stats)
    except (json.JSONDecodeError, TypeError):
        return 50.0

    # Stats may be a list of season entries — use the most recent one
    if isinstance(stats, list):
        if not stats:
            return 50.0
        stats = stats[-1]

    # Try OPS for hitters, ERA for pitchers
    ops = stats.get("ops") or stats.get("OPS")
    era = stats.get("era") or stats.get("ERA")

    if ops is not None:
        try:
            ops = float(ops)
            if ops > 0.900:
                return 90.0
            if ops > 0.800:
                return 70.0
            if ops > 0.700:
                return 50.0
            return 30.0
        except (ValueError, TypeError):
            pass

    if era is not None:
        try:
            era = float(era)
            if era < 2.50:
                return 90.0
            if era < 3.50:
                return 70.0
            if era < 4.50:
                return 50.0
            return 30.0
        except (ValueError, TypeError):
            pass

    return 50.0


def _score_roster_need(prospect: Prospect, player: Player) -> float:
    """Score based on organizational roster need at this position."""
    # Without detailed roster analysis, use a moderate default
    # In a full implementation, this would check the parent club's
    # depth chart and injury situation
    return 50.0


def _score_proximity(prospect: Prospect) -> float:
    """Score based on how close the prospect is to MLB."""
    level = (prospect.level or "").strip()
    return float(LEVEL_SCORES.get(level, 25))


def _score_forty_man(prospect: Prospect) -> float:
    """Score based on 40-man roster status."""
    if prospect.on_40_man:
        return 80.0
    return 30.0


def _score_service_time() -> float:
    """Score based on service time considerations.

    After the Super 2 deadline (~June), teams are more willing to call up
    prospects without losing an extra year of control.
    """
    today = date.today()
    # Super 2 is roughly mid-June
    if today.month >= 7:
        return 70.0  # Past Super 2, more likely
    if today.month == 6 and today.day >= 15:
        return 60.0  # Around Super 2
    if today.month >= 4:
        return 40.0  # Pre-Super 2, teams may wait
    return 30.0  # Spring training / early season


def _score_buzz(article_count: int) -> float:
    """Score based on recent media buzz about a prospect's call-up.

    More articles mentioning a prospect in call-up context = higher score.
    """
    if article_count >= 4:
        return 95.0  # Heavy buzz — multiple sources reporting
    if article_count >= 2:
        return 80.0  # Moderate buzz — a couple of reports
    if article_count >= 1:
        return 60.0  # Some buzz — at least one report
    return 10.0  # No buzz


async def _load_buzz_counts(db: AsyncSession) -> dict[int, int]:
    """Load count of recent buzz articles per player (last 14 days)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    result = await db.execute(
        select(ProspectBuzz.player_id, func.count(ProspectBuzz.id))
        .where(ProspectBuzz.created_at >= cutoff)
        .group_by(ProspectBuzz.player_id)
    )
    return {row[0]: row[1] for row in result.all()}


async def _load_recent_buzz(db: AsyncSession) -> dict[int, list[dict]]:
    """Load recent buzz items per player for display (last 14 days, max 5 each)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    result = await db.execute(
        select(ProspectBuzz)
        .where(ProspectBuzz.created_at >= cutoff)
        .order_by(ProspectBuzz.created_at.desc())
    )
    buzz_by_player: dict[int, list[dict]] = {}
    for b in result.scalars().all():
        items = buzz_by_player.setdefault(b.player_id, [])
        if len(items) < 5:
            items.append({
                "source": b.source,
                "title": b.title,
                "url": b.url,
                "snippet": b.snippet,
                "published_at": b.published_at.isoformat() if b.published_at else None,
            })
    return buzz_by_player


async def _load_recent_callups(db: AsyncSession) -> list[dict]:
    """Load recent call-up transactions for context."""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.type == "call_up")
        .order_by(Transaction.date.desc())
        .limit(20)
    )
    return [
        {
            "player_name": t.player_name,
            "to_team": t.to_team,
            "date": t.date,
        }
        for t in result.scalars().all()
    ]
