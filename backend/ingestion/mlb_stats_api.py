"""MiLB stats fetcher using the MLB Stats API.

Resolves player MLB IDs and fetches current minor league season stats.
The MLB Stats API is free and requires no authentication.
"""

import logging
from datetime import datetime

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

# Minor league sport IDs in the MLB Stats API
MILB_SPORT_IDS = {
    11: "AAA",
    12: "AA",
    13: "High-A",
    14: "A",
    15: "Short-A",
    16: "Rookie",
}


async def resolve_mlb_id(player_name: str) -> int | None:
    """Search the MLB Stats API for a player by name and return their MLB ID."""
    url = f"{settings.mlb_stats_api_base}/people/search"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params={"names": player_name})
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, Exception) as e:
        logger.warning(f"MLB API search failed for '{player_name}': {e}")
        return None

    people = data.get("people", [])
    if not people:
        return None

    # Prefer exact name match; fall back to first result
    for person in people:
        full = person.get("fullName", "")
        if full.lower() == player_name.lower():
            return person.get("id")
    return people[0].get("id")


def _parse_splits(data: dict, group: str, results_by_level: dict[int, dict]) -> None:
    """Parse stat splits from the MLB API response into results_by_level."""
    for split_group in data.get("stats", []):
        for split in split_group.get("splits", []):
            sport = split.get("sport", {})
            sport_id = sport.get("id")
            if sport_id not in MILB_SPORT_IDS:
                continue

            stat = split.get("stat", {})
            if not stat:
                continue

            entry = results_by_level.setdefault(sport_id, {
                "level": MILB_SPORT_IDS[sport_id],
                "sport_id": sport_id,
                "hitting": None,
                "pitching": None,
            })

            if group == "hitting":
                pa = int(stat.get("plateAppearances", 0))
                k_pct = f"{(int(stat.get('strikeOuts', 0)) / pa * 100):.1f}%" if pa else "0.0%"
                bb_pct = f"{(int(stat.get('baseOnBalls', 0)) / pa * 100):.1f}%" if pa else "0.0%"
                entry["hitting"] = {
                    "avg": stat.get("avg", ".000"),
                    "ops": stat.get("ops", ".000"),
                    "hr": int(stat.get("homeRuns", 0)),
                    "sb": int(stat.get("stolenBases", 0)),
                    "k_pct": k_pct,
                    "bb_pct": bb_pct,
                    "pa": pa,
                    "games": int(stat.get("gamesPlayed", 0)),
                }
            else:
                entry["pitching"] = {
                    "era": stat.get("era", "0.00"),
                    "whip": stat.get("whip", "0.00"),
                    "k_per_9": stat.get("strikeoutsPer9Inn", "0.00"),
                    "bb_per_9": stat.get("walksPer9Inn", "0.00"),
                    "ip": stat.get("inningsPitched", "0.0"),
                    "games": int(stat.get("gamesPlayed", 0)),
                }


async def fetch_milb_stats(mlb_id: int, season: int | None = None) -> list[dict]:
    """Fetch minor league season stats for a player from the MLB Stats API.

    Returns a list of stat entries, one per minor league level the player
    appeared at during the season. Each entry has 'level', 'sport_id',
    and either 'hitting' or 'pitching' (or both).

    Falls back to the previous season if no stats are found for the current one.
    """
    if season is None:
        season = datetime.now().year

    results = await _fetch_milb_stats_for_season(mlb_id, season)
    if not results:
        results = await _fetch_milb_stats_for_season(mlb_id, season - 1)
    return results


async def _fetch_milb_stats_for_season(mlb_id: int, season: int) -> list[dict]:
    """Fetch minor league stats for a specific season."""
    sport_ids = ",".join(str(sid) for sid in MILB_SPORT_IDS)
    base = settings.mlb_stats_api_base

    results_by_level: dict[int, dict] = {}

    for group in ("hitting", "pitching"):
        url = (
            f"{base}/people/{mlb_id}/stats"
            f"?stats=season&season={season}&gameType=R"
            f"&group={group}&sportId={sport_ids}"
        )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, Exception) as e:
            logger.warning(f"MLB API stats fetch failed for mlb_id={mlb_id} group={group}: {e}")
            continue

        _parse_splits(data, group, results_by_level)

    # Sort by level (AAA first)
    return sorted(results_by_level.values(), key=lambda x: x["sport_id"])
