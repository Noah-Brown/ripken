"""Yahoo Fantasy API client."""

import argparse
import asyncio
import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.yahoo.auth import get_valid_token

logger = logging.getLogger(__name__)

YAHOO_API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"


def _extract_collection(data: dict, key: str) -> list[dict]:
    """Navigate Yahoo's deeply nested JSON to extract a list of items.

    Yahoo wraps collections in a pattern like:
      {"fantasy_content": {"users": {"0": {"user": [...]}, "count": 1}}}
    This helper walks the structure and pulls out the items.
    """
    # Walk into fantasy_content if present
    if "fantasy_content" in data:
        data = data["fantasy_content"]

    # Find the target key
    if key not in data:
        return []

    container = data[key]

    # Container is often {"0": {...}, "1": {...}, "count": N}
    items = []
    if isinstance(container, dict):
        for k, v in container.items():
            if k == "count":
                continue
            if isinstance(v, dict):
                items.append(v)
    elif isinstance(container, list):
        items = container

    return items


async def _yahoo_get(db: AsyncSession, path: str, params: dict | None = None) -> dict:
    """Authenticated GET to the Yahoo Fantasy API."""
    token = await get_valid_token(db)
    if not token:
        raise RuntimeError("No valid Yahoo token available. Please connect your Yahoo account.")

    url = f"{YAHOO_API_BASE}{path}"
    if params is None:
        params = {}
    params["format"] = "json"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def get_leagues(db: AsyncSession) -> list[dict]:
    """Fetch the user's MLB fantasy leagues for the current season."""
    data = await _yahoo_get(db, "/users;use_login=1/games;game_keys=mlb/leagues")
    # Navigate: fantasy_content -> users -> 0 -> user -> [1] -> games -> 0 -> game -> [1] -> leagues
    try:
        fc = data.get("fantasy_content", data)
        users = fc.get("users", {})
        user_data = users.get("0", {}).get("user", [])
        if len(user_data) < 2:
            return []
        games = user_data[1].get("games", {})
        game_data = games.get("0", {}).get("game", [])
        if len(game_data) < 2:
            return []
        leagues_container = game_data[1].get("leagues", {})
        leagues = []
        for k, v in leagues_container.items():
            if k == "count":
                continue
            if isinstance(v, dict) and "league" in v:
                league_info = v["league"]
                if isinstance(league_info, list) and len(league_info) > 0:
                    leagues.append(league_info[0])
                elif isinstance(league_info, dict):
                    leagues.append(league_info)
        return leagues
    except (KeyError, IndexError, TypeError):
        logger.exception("Failed to parse Yahoo leagues response.")
        return []


async def get_league_settings(db: AsyncSession, league_key: str) -> dict:
    """Fetch settings for a specific league."""
    data = await _yahoo_get(db, f"/league/{league_key}/settings")
    try:
        fc = data.get("fantasy_content", data)
        league = fc.get("league", [])
        if isinstance(league, list) and len(league) > 1:
            return league[1].get("settings", [{}])[0] if isinstance(league[1].get("settings"), list) else league[1].get("settings", {})
        return {}
    except (KeyError, IndexError, TypeError):
        logger.exception("Failed to parse league settings.")
        return {}


async def get_team_key(db: AsyncSession, league_key: str) -> str | None:
    """Get the current user's team key within a league."""
    data = await _yahoo_get(db, f"/league/{league_key}/teams")
    try:
        fc = data.get("fantasy_content", data)
        league = fc.get("league", [])
        if isinstance(league, list) and len(league) > 1:
            teams_container = league[1].get("teams", {})
            for k, v in teams_container.items():
                if k == "count":
                    continue
                if isinstance(v, dict) and "team" in v:
                    team_info = v["team"]
                    if isinstance(team_info, list) and len(team_info) > 0:
                        team_meta = team_info[0]
                        # team_meta is a list of dicts
                        if isinstance(team_meta, list):
                            for item in team_meta:
                                if isinstance(item, dict) and "is_owned_by_current_login" in item:
                                    if item["is_owned_by_current_login"] == 1:
                                        # Find team_key in the same meta list
                                        for m in team_meta:
                                            if isinstance(m, dict) and "team_key" in m:
                                                return m["team_key"]
        return None
    except (KeyError, IndexError, TypeError):
        logger.exception("Failed to parse team key.")
        return None


async def get_roster(db: AsyncSession, team_key: str) -> list[dict]:
    """Fetch roster players for a team."""
    data = await _yahoo_get(db, f"/team/{team_key}/roster/players")
    try:
        fc = data.get("fantasy_content", data)
        team = fc.get("team", [])
        if isinstance(team, list) and len(team) > 1:
            roster = team[1].get("roster", {})
            coverage_type = roster.get("0", roster)
            players_container = coverage_type.get("players", roster.get("players", {}))
            players = []
            if isinstance(players_container, dict):
                for k, v in players_container.items():
                    if k == "count":
                        continue
                    if isinstance(v, dict) and "player" in v:
                        player_data = v["player"]
                        if isinstance(player_data, list) and len(player_data) >= 2:
                            # player_data[0] is list of info dicts, player_data[1] has selected_position
                            info = {}
                            if isinstance(player_data[0], list):
                                for item in player_data[0]:
                                    if isinstance(item, dict):
                                        info.update(item)
                            # Get selected position
                            pos_data = player_data[1] if len(player_data) > 1 else {}
                            if isinstance(pos_data, dict):
                                selected = pos_data.get("selected_position", [{}])
                                if isinstance(selected, list) and len(selected) > 1:
                                    info["selected_position"] = selected[1].get("position", "")
                                elif isinstance(selected, dict):
                                    info["selected_position"] = selected.get("position", "")
                            players.append(info)
            return players
        return []
    except (KeyError, IndexError, TypeError):
        logger.exception("Failed to parse roster response.")
        return []


async def get_free_agents(
    db: AsyncSession,
    league_key: str,
    position: str | None = None,
    start: int = 0,
    count: int = 25,
) -> list[dict]:
    """Fetch free agents for a league."""
    path = f"/league/{league_key}/players;status=FA;start={start};count={count}"
    if position:
        path += f";position={position}"
    data = await _yahoo_get(db, path)
    try:
        fc = data.get("fantasy_content", data)
        league = fc.get("league", [])
        if isinstance(league, list) and len(league) > 1:
            players_container = league[1].get("players", {})
            players = []
            if isinstance(players_container, dict):
                for k, v in players_container.items():
                    if k == "count":
                        continue
                    if isinstance(v, dict) and "player" in v:
                        player_data = v["player"]
                        if isinstance(player_data, list) and len(player_data) > 0:
                            info = {}
                            if isinstance(player_data[0], list):
                                for item in player_data[0]:
                                    if isinstance(item, dict):
                                        info.update(item)
                            players.append(info)
            return players
        return []
    except (KeyError, IndexError, TypeError):
        logger.exception("Failed to parse free agents response.")
        return []


async def get_matchup(db: AsyncSession, team_key: str, week: int | None = None) -> dict:
    """Fetch matchup data for a team."""
    path = f"/team/{team_key}/matchups"
    if week is not None:
        path += f";weeks={week}"
    data = await _yahoo_get(db, path)
    try:
        fc = data.get("fantasy_content", data)
        return fc.get("team", {})
    except (KeyError, TypeError):
        logger.exception("Failed to parse matchup response.")
        return {}


# ---------------------------------------------------------------------------
# CLI entry point for manual testing
# ---------------------------------------------------------------------------


async def _cli_main():
    parser = argparse.ArgumentParser(description="Yahoo Fantasy API CLI")
    parser.add_argument("--action", required=True, choices=["leagues", "roster", "free-agents"])
    parser.add_argument("--league-key", help="Yahoo league key (e.g. 'mlb.l.12345')")
    parser.add_argument("--team-key", help="Yahoo team key (e.g. 'mlb.l.12345.t.1')")
    args = parser.parse_args()

    from backend.database.connection import async_session

    async with async_session() as db:
        if args.action == "leagues":
            leagues = await get_leagues(db)
            for lg in leagues:
                print(f"  {lg.get('league_key', '?')}: {lg.get('name', '?')}")

        elif args.action == "roster":
            if not args.team_key:
                print("--team-key required for roster action")
                return
            players = await get_roster(db, args.team_key)
            for p in players:
                print(f"  {p.get('selected_position', '?'):>3} | {p.get('name', {}).get('full', '?')}")

        elif args.action == "free-agents":
            if not args.league_key:
                print("--league-key required for free-agents action")
                return
            fas = await get_free_agents(db, args.league_key)
            for p in fas:
                print(f"  {p.get('name', {}).get('full', '?')}")


if __name__ == "__main__":
    asyncio.run(_cli_main())
