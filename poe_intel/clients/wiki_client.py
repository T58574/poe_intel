"""poewiki.net Cargo API client — game data queries."""

import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.poewiki.net/w/api.php"
_CACHE_TTL = 86400  # 24h — wiki data rarely changes mid-league
_cache: dict[str, tuple[list[dict], float]] = {}
_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": "NEXUS-PoE-Intel/1.0"},
        )
    return _client


async def _cargo_query(
    tables: str,
    fields: str,
    where: str = "",
    order_by: str = "",
    limit: int = 50,
) -> list[dict]:
    """Execute a Cargo query against poewiki.net."""
    cache_key = f"{tables}:{fields}:{where}:{order_by}:{limit}"
    cached = _cache.get(cache_key)
    if cached:
        data, ts = cached
        if time.monotonic() - ts < _CACHE_TTL:
            return data

    params = {
        "action": "cargoquery",
        "tables": tables,
        "fields": fields,
        "limit": str(limit),
        "format": "json",
    }
    if where:
        params["where"] = where
    if order_by:
        params["order_by"] = order_by

    client = await _get_client()
    resp = await client.get(BASE_URL, params=params)
    resp.raise_for_status()
    data = resp.json()

    results = [item.get("title", {}) for item in data.get("cargoquery", [])]
    _cache[cache_key] = (results, time.monotonic())
    logger.debug("wiki cargo: %s → %d results", tables, len(results))
    return results


def _sanitize_cargo(value: str) -> str:
    """Sanitize a value for use in Cargo WHERE clauses (prevent injection)."""
    return re.sub(r'["\';\\%_]', "", value).strip()[:100]


async def get_area_info(area_name: str) -> dict | None:
    """Get zone/area info: level, boss damage types, etc."""
    safe = _sanitize_cargo(area_name)
    results = await _cargo_query(
        tables="areas",
        fields="areas.name,areas.area_level,areas.boss_monster_ids,areas.area_type_tags,areas.id",
        where=f'areas.name="{safe}"',
        limit=1,
    )
    return results[0] if results else None


async def get_item_info(item_name: str) -> list[dict]:
    """Get item info from wiki."""
    safe = _sanitize_cargo(item_name)
    return await _cargo_query(
        tables="items",
        fields="items.name,items.class_id,items.rarity_id,items.required_level,items.description,items.flavour_text",
        where=f'items.name LIKE "%{safe}%"',
        limit=10,
    )


async def get_skill_gem_info(gem_name: str) -> list[dict]:
    """Get skill gem data."""
    safe = _sanitize_cargo(gem_name)
    return await _cargo_query(
        tables="skill_gems,items",
        fields="items.name,skill_gems.gem_tags,items.required_level,items.description",
        where=f'items.name LIKE "%{safe}%"',
        limit=5,
    )


async def get_versions(limit: int = 10) -> list[dict]:
    """Get recent game versions with release dates."""
    return await _cargo_query(
        tables="versions",
        fields="versions.version,versions.release_date",
        order_by="versions.release_date DESC",
        limit=limit,
    )


async def search_wiki(query: str) -> str:
    """Search poewiki.net and return formatted results."""
    items = await get_item_info(query)
    if items:
        lines = [f"Wiki results for '{query}':", ""]
        for item in items:
            name = item.get("name", "?")
            level = item.get("required level", "")
            desc = (item.get("description") or "")[:100]
            rarity = item.get("rarity id", "")
            class_id = item.get("class id", "")
            info = f"  {name} [{rarity} {class_id}] (lvl {level})"
            if desc:
                info += f" -- {desc}"
            lines.append(info)
        return "\n".join(lines)
    return f"No wiki results for '{query}'."
