"""Economy feed — periodic poe.ninja polling with trend alerts.

Runs as a background task. Stores price snapshots in fact_store.
Emits alerts on significant price movements (>15% change).

Request budget: 3 API calls per poll (1 currency + 2 item types).
Default interval: 4 hours. Total: ~18 req/day, well within 12 req/5min limit.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from utils.async_utils import safe_bg

logger = logging.getLogger(__name__)

# Tracked currencies (extracted from single currency overview call)
TRACKED_CURRENCIES = {
    "Divine Orb",
    "Exalted Orb",
    "Mirror of Kalandra",
    "Fracturing Orb",
    "Awakener's Orb",
}

# Tracked uniques grouped by type (one API call per type)
_TRACKED_BY_TYPE: dict[str, set[str]] = {
    "UniqueAccessory": {
        "Mageblood",
        "Headhunter",
        "Ashes of the Stars",
        "Nimis",
        "Crystallised Omniscience",
    },
    "UniqueArmour": {"Aegis Aurora", "The Squire"},
}

ALERT_THRESHOLD_PCT = 15.0

# Default: poll every 4 hours (safe for rate limits)
DEFAULT_INTERVAL = 4 * 3600


@dataclass
class PriceSnapshot:
    name: str
    chaos_value: float
    timestamp: float


class EconomyFeed:
    """Background economy monitor with trend detection."""

    def __init__(self, ninja_client, fact_store=None, alert_callback=None):
        self.ninja = ninja_client
        self.fact_store = fact_store
        self.alert_callback = alert_callback
        self._history: dict[str, list[PriceSnapshot]] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self, interval: int = DEFAULT_INTERVAL):
        """Start the feed loop."""
        if self._running:
            return
        self._running = True
        self._task = safe_bg(self._loop(interval), "poe_economy_feed")
        logger.info(
            "Economy feed started (interval: %ds = %.1fh)", interval, interval / 3600
        )

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Economy feed stopped")

    async def _loop(self, interval: int):
        await asyncio.sleep(30)  # Let app start up
        while self._running:
            try:
                await self._poll()
            except Exception as e:
                logger.error("Economy feed poll failed: %s", e)
            await asyncio.sleep(interval)

    async def _poll(self):
        """Single poll: 1 currency call + N item type calls (batched)."""
        logger.info("Economy feed polling...")
        now = time.time()

        # 1 API call: currency overview
        try:
            rates = await self.ninja.get_currency_overview()
            for rate in rates:
                if rate.name in TRACKED_CURRENCIES:
                    await self._record(rate.name, rate.chaos_equivalent, now)
        except Exception as e:
            logger.warning("Currency poll failed: %s", e)

        # 1 API call per item type (2 calls for 2 types)
        for item_type, tracked_names in _TRACKED_BY_TYPE.items():
            try:
                all_items = await self.ninja.get_item_overview(item_type)
                tracked_lower = {n.lower() for n in tracked_names}
                for item in all_items:
                    if item.name.lower() in tracked_lower:
                        await self._record(item.name, item.chaos_value, now)
            except Exception as e:
                logger.warning("Item poll failed for %s: %s", item_type, e)
            await asyncio.sleep(2)  # Breathing room between calls

        logger.info("Economy feed poll done (%d tracked items)", len(self._history))

    async def _record(self, name: str, chaos_value: float, timestamp: float):
        snap = PriceSnapshot(name=name, chaos_value=chaos_value, timestamp=timestamp)
        history = self._history.setdefault(name, [])
        history.append(snap)
        if len(history) > 168:
            history[:] = history[-168:]

        # Alert on significant change
        if len(history) >= 2:
            prev = history[-2]
            if prev.chaos_value > 0:
                change_pct = ((chaos_value - prev.chaos_value) / prev.chaos_value) * 100
                if abs(change_pct) >= ALERT_THRESHOLD_PCT:
                    direction = "up" if change_pct > 0 else "down"
                    msg = (
                        f"[PoE Economy] {name}: {prev.chaos_value:.0f}c -> "
                        f"{chaos_value:.0f}c ({change_pct:+.1f}% {direction})"
                    )
                    logger.info(msg)
                    if self.alert_callback:
                        try:
                            await self.alert_callback(msg)
                        except Exception as e:
                            logger.warning("Alert callback failed: %s", e)

        if self.fact_store:
            try:
                await self.fact_store.store_fact(
                    subject=f"poe_price:{name}",
                    predicate="chaos_value",
                    obj=str(round(chaos_value)),
                    confidence=0.95,
                )
            except Exception as e:
                logger.debug("Fact store write failed: %s", e)

    def get_summary(self) -> str:
        if not self._history:
            return "No price data collected yet."

        lines = ["=== Economy Snapshot ===", ""]

        currency_lines = []
        for name in sorted(TRACKED_CURRENCIES):
            history = self._history.get(name)
            if history:
                latest = history[-1]
                trend = ""
                if len(history) >= 2:
                    prev = history[-2]
                    if prev.chaos_value > 0:
                        change = (
                            (latest.chaos_value - prev.chaos_value) / prev.chaos_value
                        ) * 100
                        trend = f" ({change:+.1f}%)"
                currency_lines.append(f"  {name}: {latest.chaos_value:,.0f}c{trend}")

        if currency_lines:
            lines.append("Currencies:")
            lines.extend(currency_lines)
            lines.append("")

        unique_lines = []
        for item_type, names in _TRACKED_BY_TYPE.items():
            for item_name in sorted(names):
                for stored_name, history in self._history.items():
                    if item_name.lower() in stored_name.lower() and history:
                        latest = history[-1]
                        unique_lines.append(
                            f"  {stored_name}: {latest.chaos_value:,.0f}c"
                        )
                        break

        if unique_lines:
            lines.append("Key Uniques:")
            lines.extend(unique_lines)

        return "\n".join(lines)
