"""Alert generation logic.

Generates alerts after data syncs for events like:
- Lineup posted / unexpected bench
- Call-ups
- Reliever role changes
- IL moves
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.models import (
    Alert,
    Lineup,
    Player,
    RelieverRole,
    Transaction,
    UserRoster,
    UserWatchlist,
)

logger = logging.getLogger(__name__)


async def generate_alerts(db: AsyncSession) -> int:
    """Run all alert checks and store new alerts. Returns count of new alerts."""
    today = date.today().isoformat()
    total = 0

    total += await _check_callup_alerts(db, today)
    total += await _check_il_alerts(db, today)
    total += await _check_role_change_alerts(db, today)

    if total > 0:
        logger.info(f"Generated {total} new alerts.")
    return total


async def _check_callup_alerts(db: AsyncSession, today: str) -> int:
    """Check for prospect call-ups in recent transactions."""
    # Get watched player IDs
    watched_ids = await _get_watched_player_ids(db)
    if not watched_ids:
        return 0

    # Recent call-up transactions
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    result = await db.execute(
        select(Transaction)
        .where(
            Transaction.type == "call_up",
            Transaction.date >= yesterday,
        )
    )
    transactions = result.scalars().all()

    count = 0
    for txn in transactions:
        if txn.player_id and txn.player_id in watched_ids:
            # Check if alert already exists
            if await _alert_exists(db, txn.player_id, "callup", today):
                continue

            player_name = txn.player_name or "Unknown"
            alert = Alert(
                player_id=txn.player_id,
                alert_type="callup",
                message=f"{player_name} has been called up to {txn.to_team or 'MLB'}.",
            )
            db.add(alert)
            count += 1

    if count:
        await db.commit()
    return count


async def _check_il_alerts(db: AsyncSession, today: str) -> int:
    """Check for IL moves affecting rostered players."""
    roster_ids = await _get_roster_player_ids(db)
    if not roster_ids:
        return 0

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    result = await db.execute(
        select(Transaction)
        .where(
            Transaction.type.in_(["IL", "IL_return"]),
            Transaction.date >= yesterday,
        )
    )
    transactions = result.scalars().all()

    count = 0
    for txn in transactions:
        if txn.player_id and txn.player_id in roster_ids:
            if await _alert_exists(db, txn.player_id, "il_move", today):
                continue

            player_name = txn.player_name or "Unknown"
            action = "placed on the IL" if txn.type == "IL" else "activated from the IL"
            alert = Alert(
                player_id=txn.player_id,
                alert_type="il_move",
                message=f"{player_name} has been {action}.",
            )
            db.add(alert)
            count += 1

    if count:
        await db.commit()
    return count


async def _check_role_change_alerts(db: AsyncSession, today: str) -> int:
    """Check for reliever role changes (comparing today vs 7 days ago)."""
    roster_ids = await _get_roster_player_ids(db)
    watched_ids = await _get_watched_player_ids(db)
    relevant_ids = roster_ids | watched_ids
    if not relevant_ids:
        return 0

    seven_days_ago = (date.today() - timedelta(days=7)).isoformat()

    # Current roles
    current_result = await db.execute(
        select(RelieverRole)
        .where(RelieverRole.date == today)
    )
    current_roles = {r.player_id: r.role for r in current_result.scalars().all()}

    # Previous roles
    old_result = await db.execute(
        select(RelieverRole)
        .where(RelieverRole.date == seven_days_ago)
    )
    old_roles = {r.player_id: r.role for r in old_result.scalars().all()}

    count = 0
    for pid in relevant_ids:
        old_role = old_roles.get(pid)
        new_role = current_roles.get(pid)

        if old_role and new_role and old_role != new_role:
            if await _alert_exists(db, pid, "role_change", today):
                continue

            # Get player name
            player_result = await db.execute(
                select(Player.full_name).where(Player.id == pid)
            )
            name = player_result.scalar_one_or_none() or "Unknown"

            alert = Alert(
                player_id=pid,
                alert_type="role_change",
                message=f"{name} role changed from {old_role} to {new_role}.",
            )
            db.add(alert)
            count += 1

    if count:
        await db.commit()
    return count


async def _get_roster_player_ids(db: AsyncSession) -> set[int]:
    """Get all player IDs on user's rosters."""
    result = await db.execute(
        select(UserRoster.player_id).where(UserRoster.player_id.isnot(None))
    )
    return {row[0] for row in result.all()}


async def _get_watched_player_ids(db: AsyncSession) -> set[int]:
    """Get all player IDs on watchlist + roster."""
    roster_ids = await _get_roster_player_ids(db)
    result = await db.execute(select(UserWatchlist.player_id))
    watchlist_ids = {row[0] for row in result.all()}
    return roster_ids | watchlist_ids


async def _alert_exists(
    db: AsyncSession, player_id: int, alert_type: str, today: str
) -> bool:
    """Check if an alert already exists for this player/type today."""
    result = await db.execute(
        select(Alert.id).where(
            Alert.player_id == player_id,
            Alert.alert_type == alert_type,
            Alert.created_at >= today,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None
