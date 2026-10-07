"""
Sleeper Fantasy Football MCP Server
------------------------------------
Wraps Sleeper's free, public, read-only API (https://docs.sleeper.com/)
as an MCP server, so Claude can pull live league data: rosters, matchups,
transactions, and league settings, for any Sleeper league.

No API key or login needed -- Sleeper's API is open and read-only.

Run locally (stdio, for testing with Claude Desktop):
    python server.py

Run as a remote server (for claude.ai custom connectors):
    python server.py --http
(or just deploy it -- see README.md; hosts like Render set $PORT and
 this file is already wired to read it.)
"""

import os
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

SLEEPER_BASE = "https://api.sleeper.app/v1"

mcp = FastMCP(
    "sleeper-fantasy-football",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8000)),
    stateless_http=True,
)

# Sleeper's full NFL player directory is ~5MB and only changes a few times
# a day. We fetch it once per server process and cache it in memory instead
# of re-downloading it on every single tool call.
_players_cache: dict[str, Any] | None = None


async def _get_players_cache(client: httpx.AsyncClient) -> dict[str, Any]:
    global _players_cache
    if _players_cache is None:
        resp = await client.get(f"{SLEEPER_BASE}/players/nfl", timeout=30)
        resp.raise_for_status()
        _players_cache = resp.json()
    return _players_cache


def _player_label(player_id: str, players: dict[str, Any]) -> str:
    p = players.get(player_id)
    if not p:
        return f"Unknown player ({player_id})"
    name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    pos = p.get("position") or "?"
    team = p.get("team") or "FA"
    injury = p.get("injury_status")
    suffix = f" [{injury}]" if injury else ""
    return f"{name} ({pos} - {team}){suffix}"


@mcp.tool()
async def find_my_leagues(username: str, season: str = "2026") -> list[dict]:
    """Find all Sleeper fantasy football leagues for a given Sleeper username in a
    given season. Use this first if you don't already know your league_id --
    every other tool needs it."""
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(f"{SLEEPER_BASE}/user/{username}")
        user_resp.raise_for_status()
        user = user_resp.json()
        if not user:
            return []
        leagues_resp = await client.get(
            f"{SLEEPER_BASE}/user/{user['user_id']}/leagues/nfl/{season}"
        )
        leagues_resp.raise_for_status()
        return [
            {"league_id": l["league_id"], "name": l["name"], "season": l["season"]}
            for l in leagues_resp.json()
        ]


@mcp.tool()
async def get_league_info(league_id: str) -> dict:
    """Get basic settings for a Sleeper league: name, season, status, scoring
    settings (PPR type, TD points, etc.), and roster position requirements."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{SLEEPER_BASE}/league/{league_id}")
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def get_league_users(league_id: str) -> list[dict]:
    """Get every team owner in a Sleeper league: their Sleeper username,
    display name, and team name, mapped by user_id."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{SLEEPER_BASE}/league/{league_id}/users")
        resp.raise_for_status()
        users = resp.json()
        return [
            {
                "user_id": u.get("user_id"),
                "display_name": u.get("display_name"),
                "team_name": (u.get("metadata") or {}).get("team_name")
                or u.get("display_name"),
            }
            for u in users
        ]


@mcp.tool()
async def get_all_rosters(league_id: str) -> list[dict]:
    """Get every team's full current roster in a Sleeper league: starters,
    bench, and IR, with readable player names/positions/NFL teams, plus each
    team's record and points. This is the main tool for seeing exactly what
    every team in the league currently has -- use it before giving trade,
    waiver, or league-landscape advice."""
    async with httpx.AsyncClient() as client:
        rosters_resp = await client.get(f"{SLEEPER_BASE}/league/{league_id}/rosters")
        rosters_resp.raise_for_status()
        rosters = rosters_resp.json()

        users_resp = await client.get(f"{SLEEPER_BASE}/league/{league_id}/users")
        users_resp.raise_for_status()
        users = {u["user_id"]: u for u in users_resp.json()}

        players = await _get_players_cache(client)

        result = []
        for r in rosters:
            owner = users.get(r.get("owner_id"), {})
            team_name = (
                (owner.get("metadata") or {}).get("team_name")
                or owner.get("display_name")
                or "Unknown Team"
            )
            starter_ids = [pid for pid in (r.get("starters") or []) if pid and pid != "0"]
            reserve_ids = set(r.get("reserve") or [])
            taxi_ids = set(r.get("taxi") or [])
            all_ids = set(r.get("players") or [])
            bench_ids = all_ids - set(starter_ids) - reserve_ids - taxi_ids

            settings = r.get("settings") or {}
            result.append(
                {
                    "team_name": team_name,
                    "owner_display_name": owner.get("display_name"),
                    "record": {
                        "wins": settings.get("wins"),
                        "losses": settings.get("losses"),
                        "ties": settings.get("ties"),
                    },
                    "points_for": settings.get("fpts"),
                    "points_against": settings.get("fpts_against"),
                    "starters": [_player_label(pid, players) for pid in starter_ids],
                    "bench": [_player_label(pid, players) for pid in bench_ids],
                    "injured_reserve": [_player_label(pid, players) for pid in reserve_ids],
                    "taxi_squad": [_player_label(pid, players) for pid in taxi_ids],
                }
            )
        return result


@mcp.tool()
async def get_matchups(league_id: str, week: int) -> list[dict]:
    """Get head-to-head fantasy matchup scores for a given week in a Sleeper
    league, including each team's starters and their live/final points."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{SLEEPER_BASE}/league/{league_id}/matchups/{week}")
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def get_transactions(league_id: str, week: int) -> list[dict]:
    """Get waiver adds/drops and trades that occurred in a given week of a
    Sleeper league -- use this to see what other teams have been doing."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{SLEEPER_BASE}/league/{league_id}/transactions/{week}")
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def get_player_info(player_ids: list[str]) -> list[dict]:
    """Look up NFL player details (name, position, team, roster status, injury
    status) by Sleeper player ID. Get player IDs from get_all_rosters or
    get_matchups first."""
    async with httpx.AsyncClient() as client:
        players = await _get_players_cache(client)
        out = []
        for pid in player_ids:
            p = players.get(pid)
            if p:
                out.append(
                    {
                        "player_id": pid,
                        "name": p.get("full_name"),
                        "position": p.get("position"),
                        "team": p.get("team"),
                        "status": p.get("status"),
                        "injury_status": p.get("injury_status"),
                    }
                )
            else:
                out.append({"player_id": pid, "error": "not found"})
        return out


if __name__ == "__main__":
    # Supports two modes:
    #   python server.py          -> stdio transport (local use, e.g. Claude Desktop)
    #   python server.py --http   -> streamable-http transport (remote/custom connector)
    # Hosting platforms (Render, Railway, etc.) set $PORT, which is already
    # wired into the FastMCP() constructor above, so deploying just needs the
    # start command to pass --http (see README.md).
    if "--http" in sys.argv or os.environ.get("MCP_TRANSPORT") == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
