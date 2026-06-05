"""GGG Public API client — character data, ladder, leagues.

Uses public endpoints that don't require OAuth.
Reuses a module-level httpx client for connection pooling.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.pathofexile.com"

_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "NEXUS-PoE-Intel/1.0"},
        )
    return _client


async def _get(path: str, params: dict | None = None) -> httpx.Response:
    """GET request to GGG API with shared client."""
    client = await _get_client()
    resp = await client.get(f"{BASE_URL}{path}", params=params)
    resp.raise_for_status()
    return resp


async def get_characters(account_name: str) -> list[dict]:
    """Get public character list for an account."""
    resp = await _get("/character-window/get-characters", {"accountName": account_name})
    return resp.json()


async def get_character_items(account_name: str, character_name: str) -> dict:
    """Get equipped items for a character."""
    resp = await _get(
        "/character-window/get-items",
        {"accountName": account_name, "character": character_name},
    )
    return resp.json()


async def get_passive_skills(account_name: str, character_name: str) -> dict:
    """Get passive tree allocation for a character."""
    resp = await _get(
        "/character-window/get-passive-skills",
        {"accountName": account_name, "character": character_name},
    )
    return resp.json()


async def get_ladder(league: str, limit: int = 20, offset: int = 0) -> dict:
    """Get league ladder (public, no auth)."""
    resp = await _get(f"/api/ladders/{league}", {"offset": offset, "limit": limit})
    return resp.json()


async def get_leagues() -> list[dict]:
    """Get active leagues."""
    resp = await _get("/api/leagues", {"type": "main", "compact": "1"})
    return resp.json()


async def get_character_summary(account_name: str, character_name: str) -> str:
    """Get a formatted summary of a character from GGG API."""
    try:
        chars = await get_characters(account_name)
    except Exception as e:
        return f"Error fetching characters for '{account_name}': {e}"

    char = None
    for c in chars:
        if c.get("name", "").lower() == character_name.lower():
            char = c
            break

    if not char:
        available = [c.get("name", "?") for c in chars[:10]]
        return (
            f"Character '{character_name}' not found on account '{account_name}'.\n"
            f"Available: {', '.join(available)}"
        )

    lines = [
        f"Character: {char.get('name')} ({char.get('class', '?')})",
        f"Level: {char.get('level', '?')}",
        f"League: {char.get('league', '?')}",
    ]

    try:
        items_data = await get_character_items(account_name, character_name)
        items = items_data.get("items", [])
        if items:
            lines.append(f"\nEquipped items: {len(items)}")
            for item in items:
                name = item.get("name", "")
                base = item.get("typeLine", "")
                slot = item.get("inventoryId", "")
                rarity = {0: "Normal", 1: "Magic", 2: "Rare", 3: "Unique"}.get(
                    item.get("frameType", 0), "?"
                )
                display = name if name else base
                if name and base:
                    display = f"{name} {base}"
                lines.append(f"  [{slot}] {display} ({rarity})")
    except Exception as e:
        lines.append(f"\nItems: private or error ({e})")

    return "\n".join(lines)
