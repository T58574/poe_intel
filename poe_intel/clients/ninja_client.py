"""poe.ninja API client — async with rate limiting and caching."""

import logging
import time

import httpx

from poe_intel.models import CurrencyRate, PriceInfo

logger = logging.getLogger(__name__)

# poe.ninja migrated to new URL scheme in 2025
BASE_URL = "https://poe.ninja/poe1/api/economy/stash/current"

# Valid item types for itemoverview endpoint
ITEM_TYPES = [
    "Oil",
    "Incubator",
    "Scarab",
    "Fossil",
    "Resonator",
    "Essence",
    "DivinationCard",
    "SkillGem",
    "BaseType",
    "UniqueMap",
    "Map",
    "UniqueJewel",
    "UniqueFlask",
    "UniqueWeapon",
    "UniqueArmour",
    "UniqueAccessory",
    "Beast",
    "Vial",
    "DeliriumOrb",
    "Omen",
    "UniqueRelic",
    "ClusterJewel",
    "BlightedMap",
    "BlightRavagedMap",
    "Invitation",
    "Memory",
    "Coffin",
    "AllflameEmber",
]

# Types that go through currencyoverview (not itemoverview)
CURRENCY_TYPES = ["Currency", "Fragment"]

# Rate limit: 12 requests per 5 minutes
_RATE_WINDOW = 300  # seconds
_RATE_LIMIT = 12


class NinjaClient:
    """Async poe.ninja API client with built-in rate limiter and cache."""

    def __init__(self, league: str = "Mirage", cache_ttl: int = 3600):
        self.league = league
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[dict, float]] = {}
        self._request_times: list[float] = []
        self._client: httpx.AsyncClient | None = None

    def _check_rate_limit(self) -> None:
        """Enforce 12 req / 5 min rate limit."""
        now = time.monotonic()
        self._request_times = [t for t in self._request_times if now - t < _RATE_WINDOW]
        if len(self._request_times) >= _RATE_LIMIT:
            wait = _RATE_WINDOW - (now - self._request_times[0])
            raise RuntimeError(f"poe.ninja rate limit reached. Retry in {wait:.0f}s.")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create a reusable httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=20,
                headers={"User-Agent": "NEXUS-PoE-Intel/1.0"},
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _get_cached(self, key: str) -> dict | None:
        cached = self._cache.get(key)
        if cached:
            data, ts = cached
            if time.monotonic() - ts < self.cache_ttl:
                return data
            del self._cache[key]
        return None

    async def _fetch(self, endpoint: str, params: dict) -> dict:
        cache_key = f"{endpoint}:{params}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("ninja cache hit: %s", cache_key)
            return cached

        self._check_rate_limit()

        url = f"{BASE_URL}/{endpoint}"
        client = await self._get_client()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        self._request_times.append(time.monotonic())
        self._cache[cache_key] = (data, time.monotonic())
        logger.debug(
            "ninja fetch: %s %s → %d items",
            endpoint,
            params,
            len(data.get("lines", [])),
        )
        return data

    async def get_currency_overview(self) -> list[CurrencyRate]:
        """Get currency exchange rates (chaos equivalent)."""
        data = await self._fetch(
            "currency/overview",
            {"league": self.league, "type": "Currency"},
        )
        # Fallback to Standard if league has no data yet (league just started)
        if not data.get("lines") and self.league != "Standard":
            logger.info("No data for %s, falling back to Standard", self.league)
            data = await self._fetch(
                "currency/overview",
                {"league": "Standard", "type": "Currency"},
            )
        rates = []
        for line in data.get("lines", []):
            sparkline = line.get("receiveSparkLine") or {}
            rates.append(
                CurrencyRate(
                    name=line.get("currencyTypeName", ""),
                    chaos_equivalent=line.get("chaosEquivalent", 0),
                    change_pct=sparkline.get("totalChange", 0),
                    icon=_find_icon(data, line.get("currencyTypeName", "")),
                )
            )
        return sorted(rates, key=lambda r: r.chaos_equivalent, reverse=True)

    async def get_item_overview(self, item_type: str) -> list[PriceInfo]:
        """Get item prices by type (e.g. UniqueArmour, SkillGem)."""
        if item_type in CURRENCY_TYPES:
            endpoint = "currency/overview"
        else:
            endpoint = "item/overview"

        data = await self._fetch(endpoint, {"league": self.league, "type": item_type})
        # Fallback to Standard if league has no data yet
        if not data.get("lines") and self.league != "Standard":
            logger.info(
                "No data for %s/%s, falling back to Standard", self.league, item_type
            )
            data = await self._fetch(
                endpoint, {"league": "Standard", "type": item_type}
            )

        items = []
        for line in data.get("lines", []):
            sparkline = line.get("sparkline") or line.get("receiveSparkLine") or {}
            items.append(
                PriceInfo(
                    name=line.get("name") or line.get("currencyTypeName", ""),
                    chaos_value=line.get("chaosValue")
                    or line.get("chaosEquivalent", 0),
                    divine_value=line.get("divineValue", 0),
                    exalted_value=line.get("exaltedValue", 0),
                    listing_count=line.get("listingCount", 0),
                    change_pct=sparkline.get("totalChange", 0),
                    icon=line.get("icon", ""),
                    details_id=line.get("detailsId", ""),
                )
            )
        return items

    async def search_item(
        self, query: str, item_type: str | None = None
    ) -> list[PriceInfo]:
        """Search items by name across one or multiple types."""
        query_lower = query.lower()
        results: list[PriceInfo] = []

        types_to_search = [item_type] if item_type else _guess_types(query)
        for t in types_to_search:
            try:
                items = await self.get_item_overview(t)
                for item in items:
                    if query_lower in item.name.lower():
                        results.append(item)
            except Exception as e:
                logger.warning("search_item failed for type %s: %s", t, e)

        return sorted(results, key=lambda i: i.chaos_value, reverse=True)

    async def get_top_skills(self, limit: int = 20) -> list[PriceInfo]:
        """Get most expensive skill gems (proxy for popularity)."""
        items = await self.get_item_overview("SkillGem")
        return sorted(items, key=lambda i: i.chaos_value, reverse=True)[:limit]


def _find_icon(data: dict, currency_name: str) -> str:
    for detail in data.get("currencyDetails", []):
        if detail.get("name") == currency_name:
            return detail.get("icon", "")
    return ""


def _guess_types(query: str) -> list[str]:
    """Guess which item types to search based on query."""
    q = query.lower()
    if any(w in q for w in ["flask", "bottled", "sulphur"]):
        return ["UniqueFlask"]
    if any(w in q for w in ["jewel", "timeless", "watcher"]):
        return ["UniqueJewel"]
    if any(w in q for w in ["gem", "support", "awakened", "vaal"]):
        return ["SkillGem"]
    if any(w in q for w in ["map", "guardian", "elder", "shaper"]):
        return ["UniqueMap", "Map"]
    if any(w in q for w in ["card", "divination", "the "]):
        return ["DivinationCard"]
    if any(w in q for w in ["scarab"]):
        return ["Scarab"]
    if any(w in q for w in ["essence"]):
        return ["Essence"]
    if any(w in q for w in ["fossil"]):
        return ["Fossil"]
    if any(w in q for w in ["oil"]):
        return ["Oil"]
    # Default: search uniques (most common query)
    return [
        "UniqueWeapon",
        "UniqueArmour",
        "UniqueAccessory",
        "UniqueFlask",
        "UniqueJewel",
    ]
