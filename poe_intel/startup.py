"""POE Intel startup — initializes all PoE subsystems.

Called from NEXUS main.py during initialization.
Starts economy feed and log watcher if configured.
"""

import logging

from config import settings
from poe_intel.clients.ninja_client import NinjaClient
from poe_intel.feeds.economy_feed import EconomyFeed
from poe_intel.monitor.handlers import GameTracker, setup_handlers
from poe_intel.monitor.log_watcher import LogWatcher
from poe_intel.tools import set_economy_feed

logger = logging.getLogger(__name__)

# Global references for cleanup
_watcher: LogWatcher | None = None
_feed: EconomyFeed | None = None
_tracker: GameTracker | None = None


async def init_poe_intel(fact_store=None, alert_callback=None):
    """Initialize POE Intel subsystems based on config.

    Args:
        fact_store: NEXUS FactStore instance for persisting price data.
        alert_callback: async fn(message: str) for sending alerts (e.g. Telegram).
    """
    global _watcher, _feed, _tracker

    league = settings.poe_league
    if not league:
        logger.info("POE Intel disabled (poe_league not set)")
        return

    logger.info("Initializing POE Intel for league: %s", league)

    # Economy feed
    ninja = NinjaClient(
        league=league,
        cache_ttl=settings.poe_ninja_cache_ttl,
    )
    _feed = EconomyFeed(
        ninja_client=ninja,
        fact_store=fact_store,
        alert_callback=alert_callback,
    )
    set_economy_feed(_feed)
    await _feed.start()  # Default: 4h interval (3 API calls per poll)

    # Client.txt monitor
    log_path = settings.poe_client_log
    if log_path and settings.poe_monitor_enabled:
        _tracker = GameTracker()
        if alert_callback:
            _tracker.set_alert_callback(alert_callback)
        _watcher = LogWatcher(log_path)
        setup_handlers(_watcher, _tracker)
        await _watcher.start()
        logger.info("Client.txt monitor active: %s", log_path)
    else:
        logger.info(
            "Client.txt monitor disabled (poe_client_log not set or monitor disabled)"
        )


async def shutdown_poe_intel():
    """Gracefully stop all POE Intel subsystems and close HTTP clients."""
    global _feed, _watcher, _tracker

    if _feed:
        await _feed.stop()
        if _feed.ninja._client:
            await _feed.ninja.close()
    if _watcher:
        await _watcher.stop()

    # Close module-level HTTP clients
    from poe_intel.clients import ggg_client, wiki_client

    for mod in [ggg_client, wiki_client]:
        client = getattr(mod, "_client", None)
        if client and not client.is_closed:
            await client.aclose()

    # Clear globals to allow re-init
    _feed = None
    _watcher = None
    _tracker = None
    logger.info("POE Intel shutdown complete")


def get_tracker() -> GameTracker | None:
    """Get the active game tracker (for tools/API)."""
    return _tracker


def get_watcher() -> LogWatcher | None:
    """Get the active log watcher."""
    return _watcher
