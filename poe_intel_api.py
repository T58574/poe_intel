"""PoE Intel API — build parsing, economy data, monitor status, isolated chat."""

import logging

from fastapi import Depends
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)


def register_poe_intel_routes(app, auth_dep):
    @app.get("/api/poe/status")
    async def poe_status(_=Depends(auth_dep)):
        """Overall PoE Intel status."""
        from config import settings
        from poe_intel.startup import get_tracker, get_watcher, _feed

        monitor_active = get_watcher() is not None and get_watcher()._running
        feed_active = _feed is not None and _feed._running

        tracker = get_tracker()
        game_status = None
        if tracker:
            game_status = {
                "current_area": tracker.current_area,
                "death_count": tracker.death_count,
                "character_name": tracker.character_name,
                "character_class": tracker.character_class,
                "character_level": tracker.character_level,
                "deaths_by_area": dict(tracker.deaths_by_area),
            }

        return JSONResponse(
            {
                "league": settings.poe_league,
                "monitor_enabled": settings.poe_monitor_enabled,
                "monitor_active": monitor_active,
                "feed_active": feed_active,
                "game_status": game_status,
            }
        )

    @app.get("/api/poe/economy/currency")
    async def poe_currency(_=Depends(auth_dep)):
        """Current currency rates."""
        from poe_intel.tools import _get_ninja

        ninja = _get_ninja()
        rates = await ninja.get_currency_overview()
        return JSONResponse(
            [
                {
                    "name": r.name,
                    "chaos_equivalent": r.chaos_equivalent,
                    "change_pct": r.change_pct,
                    "icon": r.icon,
                }
                for r in rates[:30]
            ]
        )

    @app.get("/api/poe/economy/items/{item_type}")
    async def poe_items(item_type: str, _=Depends(auth_dep)):
        """Item prices by type."""
        from poe_intel.clients.ninja_client import ITEM_TYPES, CURRENCY_TYPES
        from poe_intel.tools import _get_ninja

        valid = ITEM_TYPES + CURRENCY_TYPES
        if item_type not in valid:
            return JSONResponse(
                {"error": f"Invalid type. Valid: {valid}"}, status_code=400
            )

        ninja = _get_ninja()
        items = await ninja.get_item_overview(item_type)
        return JSONResponse(
            [
                {
                    "name": i.name,
                    "chaos_value": i.chaos_value,
                    "divine_value": i.divine_value,
                    "listing_count": i.listing_count,
                    "change_pct": i.change_pct,
                    "icon": i.icon,
                }
                for i in sorted(items, key=lambda x: x.chaos_value, reverse=True)[:50]
            ]
        )

    @app.post("/api/poe/build/parse")
    async def poe_parse_build(body: dict, _=Depends(auth_dep)):
        """Parse a PoB code or URL."""
        code = body.get("code", "").strip()
        if not code:
            return JSONResponse({"error": "code is required"}, status_code=400)

        from poe_intel.clients.pob_decoder import decode_build

        try:
            build = await decode_build(code)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

        s = build.stats
        return JSONResponse(
            {
                "class_name": s.class_name,
                "ascendancy": s.ascendancy,
                "level": s.level,
                "offense": {
                    "total_dps": s.total_dps,
                    "total_dot": s.total_dot,
                    "crit_chance": s.crit_chance,
                    "crit_multiplier": s.crit_multiplier,
                    "attack_speed": s.attack_speed,
                    "cast_speed": s.cast_speed,
                },
                "defense": {
                    "life": s.life,
                    "energy_shield": s.energy_shield,
                    "armour": s.armour,
                    "evasion": s.evasion,
                    "block_chance": s.block_chance,
                    "spell_block": s.spell_block,
                },
                "resistances": {
                    "fire": s.fire_res,
                    "cold": s.cold_res,
                    "lightning": s.lightning_res,
                    "chaos": s.chaos_res,
                },
                "skills": [
                    {
                        "slot": sg.slot,
                        "gems": sg.gems,
                        "is_main": sg.is_main,
                    }
                    for sg in build.skills
                ],
                "items": [
                    {
                        "name": i.name,
                        "base": i.base,
                        "rarity": i.rarity,
                        "slot": i.slot,
                    }
                    for i in build.items
                    if i.name
                ],
                "notes": build.notes[:500] if build.notes else "",
            }
        )

    @app.get("/api/poe/monitor/events")
    async def poe_monitor_events(_=Depends(auth_dep)):
        """Recent game events from Client.txt monitor."""
        from poe_intel.startup import get_watcher

        watcher = get_watcher()
        if not watcher:
            return JSONResponse({"events": [], "active": False})

        events = [
            {
                "timestamp": ev.timestamp,
                "event_type": ev.event_type,
                "data": ev.data,
            }
            for ev in watcher.recent_events[-50:]
        ]
        return JSONResponse({"events": events, "active": watcher._running})

    @app.get("/api/poe/economy/snapshot")
    async def poe_economy_snapshot(_=Depends(auth_dep)):
        """Economy feed snapshot (tracked items)."""
        from poe_intel.startup import _feed

        if not _feed or not _feed._history:
            return JSONResponse({"items": [], "active": False})

        items = []
        for name, history in _feed._history.items():
            if history:
                latest = history[-1]
                prev_value = history[-2].chaos_value if len(history) >= 2 else None
                items.append(
                    {
                        "name": name,
                        "chaos_value": latest.chaos_value,
                        "prev_value": prev_value,
                        "timestamp": latest.timestamp,
                    }
                )

        return JSONResponse(
            {
                "items": sorted(items, key=lambda x: x["chaos_value"], reverse=True),
                "active": _feed._running,
            }
        )

    @app.get("/api/poe/ladder/{league}")
    async def poe_ladder_api(
        league: str, limit: int = 50, offset: int = 0, _=Depends(auth_dep)
    ):
        """Proxy to GGG ladder API (avoids CORS issues)."""
        from poe_intel.clients.ggg_client import get_ladder

        try:
            data = await get_ladder(league, limit=min(limit, 200), offset=offset)
            return JSONResponse(data)
        except Exception as e:
            return JSONResponse({"error": str(e), "entries": []}, status_code=502)

    @app.get("/api/poe/character/{account_name}")
    async def poe_character_api(
        account_name: str, character: str = "", _=Depends(auth_dep)
    ):
        """Proxy to GGG character API."""
        from poe_intel.clients.ggg_client import get_characters, get_character_items

        try:
            if character:
                items = await get_character_items(account_name, character)
                return JSONResponse(items)
            else:
                chars = await get_characters(account_name)
                return JSONResponse(chars)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=502)

    # === ISOLATED POE CHAT ===

    _CLI_MODES = {"claude", "codex", "copilot", "cursor"}

    async def _get_bridge(mode: str):
        """Get or create CLI bridge for given mode. Returns bridge or None."""
        if mode == "claude":
            bridge = app.state.claude_bridge
            if bridge is None:
                from interfaces.web_server import _load_claude_settings
                from core.claude_bridge import ClaudeBridge

                cs = await _load_claude_settings()
                bridge = ClaudeBridge(
                    system_prompt=cs["system_prompt"],
                    model=cs["model"],
                    allowed_tools=cs["allowed_tools"],
                )
                app.state.claude_bridge = bridge
            return bridge
        elif mode == "codex":
            bridge = app.state.codex_bridge
            if bridge is None:
                from interfaces.web_server import _load_codex_settings
                from core.codex_bridge import CodexBridge

                cds = await _load_codex_settings()
                bridge = CodexBridge(
                    model=cds["model"],
                    sandbox=cds["sandbox"],
                    approval=cds["approval"],
                    working_dir=cds["working_dir"],
                )
                app.state.codex_bridge = bridge
            return bridge
        elif mode == "copilot":
            bridge = app.state.copilot_bridge
            if bridge is None:
                from interfaces.web_server import _load_copilot_settings
                from core.copilot_bridge import CopilotBridge

                cs = await _load_copilot_settings()
                bridge = CopilotBridge(
                    model=cs["model"],
                    system_prompt=cs["system_prompt"],
                    autopilot=cs["autopilot"],
                    allow_all=cs["allow_all"],
                    silent=cs["silent"],
                )
                app.state.copilot_bridge = bridge
            return bridge
        elif mode == "cursor":
            bridge = app.state.cursor_bridge
            if bridge is None:
                from interfaces.web_server import _load_cursor_settings
                from core.cursor_bridge import CursorBridge

                cs = await _load_cursor_settings()
                bridge = CursorBridge(
                    model=cs["model"],
                    cmd=cs["cmd"],
                    print_mode=cs["print_mode"],
                    working_dir=cs["working_dir"],
                )
                app.state.cursor_bridge = bridge
            return bridge
        return None

    @app.post("/api/poe/chat")
    async def poe_chat_endpoint(body: dict, _=Depends(auth_dep)):
        """Mode-aware PoE chat — routes via LLM tool loop or CLI bridge."""
        message = body.get("message", "").strip()
        if not message:
            return JSONResponse({"error": "message is required"}, status_code=400)

        mode = getattr(app.state, "user_mode", "auto") or "auto"

        if mode in _CLI_MODES:
            from poe_intel.chat import poe_chat_via_bridge

            try:
                bridge = await _get_bridge(mode)
                if not bridge:
                    return JSONResponse(
                        {"error": f"{mode} bridge not available"}, status_code=503
                    )
                result = await poe_chat_via_bridge(message, bridge, mode)
                return JSONResponse(result)
            except Exception as e:
                logger.error("PoE chat bridge error (%s): %s", mode, e)
                return JSONResponse({"error": str(e)}, status_code=500)
        else:
            from poe_intel.chat import poe_chat

            router = app.state.orchestrator.router
            try:
                result = await poe_chat(message, router, mode=mode)
                return JSONResponse(result)
            except Exception as e:
                logger.error("PoE chat error: %s", e)
                return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/poe/chat/clear")
    async def poe_chat_clear(_=Depends(auth_dep)):
        from poe_intel.chat import clear_history

        clear_history()
        return JSONResponse({"ok": True})

    @app.get("/api/poe/chat/history")
    async def poe_chat_history_endpoint(_=Depends(auth_dep)):
        from poe_intel.chat import get_history

        return JSONResponse({"messages": get_history()})
