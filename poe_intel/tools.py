"""POE Intel tools — registered in NEXUS tool system for LLM access."""

import logging
from pathlib import Path

from poe_intel.clients.ninja_client import NinjaClient
from poe_intel.clients.pob_decoder import decode_build
from poe_intel.clients import wiki_client
from poe_intel.clients import ggg_client

logger = logging.getLogger(__name__)

_KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

# Singleton client (lazy init with configured league)
_ninja: NinjaClient | None = None


def _get_ninja() -> NinjaClient:
    global _ninja
    if _ninja is None:
        from config import settings

        league = getattr(settings, "poe_league", "Mirage")
        cache_ttl = getattr(settings, "poe_ninja_cache_ttl", 3600)
        _ninja = NinjaClient(league=league, cache_ttl=cache_ttl)
    return _ninja


async def poe_parse_build(code_or_url: str) -> str:
    """Parse a Path of Building code or paste URL into a full build analysis.

    Returns structured AI-friendly output with diagnostics and actionable issues.
    """
    try:
        build = await decode_build(code_or_url)
    except Exception as e:
        return f"Error parsing build: {e}"

    return _format_build_analysis(build)


def _format_build_analysis(build) -> str:
    """Format ParsedBuild into structured AI-friendly analysis."""
    s = build.stats
    ehp = s.life + s.energy_shield

    lines = [
        "# BUILD SUMMARY",
        f"Class: {s.class_name} / {s.ascendancy}",
        f"Level: {s.level}",
        f"EHP (Life+ES): {ehp:,.0f}",
    ]

    # ── Offense ──
    lines += ["", "## OFFENSE"]
    lines.append(f"Total DPS: {s.total_dps:,.0f}")
    if s.total_dot:
        lines.append(f"Total DoT DPS: {s.total_dot:,.0f}")
    for label, val in [
        ("Bleed DPS", s.bleed_dps),
        ("Ignite DPS", s.ignite_dps),
        ("Poison DPS", s.poison_dps),
    ]:
        if val:
            lines.append(f"{label}: {val:,.0f}")
    if s.crit_chance:
        lines.append(
            f"Crit: {s.crit_chance:.1f}% chance, {s.crit_multiplier:.0f}% multi"
        )
    if s.hit_chance and s.hit_chance < 100:
        lines.append(f"Hit Chance: {s.hit_chance:.1f}% [!] NOT 100%")
    if s.attack_speed:
        lines.append(f"Attack Speed: {s.attack_speed:.2f}")
    if s.cast_speed:
        lines.append(f"Cast Speed: {s.cast_speed:.2f}")

    # ── Defense ──
    lines += ["", "## DEFENSE"]
    lines.append(f"Life: {s.life:,.0f}")
    if s.energy_shield:
        lines.append(f"Energy Shield: {s.energy_shield:,.0f}")
    if s.armour:
        lines.append(
            f"Armour: {s.armour:,.0f} ({s.phys_damage_reduction:.0f}% phys reduction)"
        )
    if s.evasion:
        lines.append(f"Evasion: {s.evasion:,.0f}")
    if s.block_chance:
        lines.append(f"Block: {s.block_chance:.0f}%")
    if s.spell_block:
        lines.append(f"Spell Block: {s.spell_block:.0f}%")

    # Recovery
    recovery = []
    if s.life_regen:
        recovery.append(f"Life Regen: {s.life_regen:,.0f}/s")
    if s.es_regen:
        recovery.append(f"ES Regen: {s.es_regen:,.0f}/s")
    if s.mana_regen:
        recovery.append(f"Mana Regen: {s.mana_regen:,.0f}/s")
    if recovery:
        lines += ["", "## RECOVERY"] + recovery

    # ── Resistances ──
    lines += ["", "## RESISTANCES"]
    for label, val, cap in [
        ("Fire", s.fire_res, 75),
        ("Cold", s.cold_res, 75),
        ("Lightning", s.lightning_res, 75),
        ("Chaos", s.chaos_res, 0),
    ]:
        status = ""
        if label == "Chaos":
            if val < -30:
                status = " [!!] DANGEROUSLY LOW"
            elif val < 0:
                status = " [!] NEGATIVE"
        else:
            if val < 75:
                deficit = 75 - val
                status = f" [!] UNCAPPED (need +{deficit:.0f}%)"
            elif val < 95:
                status = " (low overcap, vulnerable to Ele Weakness)"
        lines.append(f"{label}: {val:.0f}%{status}")

    # ── Attributes ──
    if s.strength or s.dexterity or s.intelligence:
        lines += [
            "",
            "## ATTRIBUTES",
            f"STR: {s.strength:.0f} | DEX: {s.dexterity:.0f} | INT: {s.intelligence:.0f}",
        ]

    # ── Mana ──
    if s.mana:
        mana_pct = (s.mana_unreserved / s.mana * 100) if s.mana else 0
        lines += [
            "",
            "## MANA",
            f"Total: {s.mana:,.0f} | Unreserved: {s.mana_unreserved:,.0f} ({mana_pct:.0f}%)",
        ]

    # ── Skills ──
    if build.skills:
        lines += ["", "## SKILL GEMS"]
        for sg in build.skills:
            if not sg.is_enabled:
                continue
            marker = "[MAIN] " if sg.is_main else ""
            slot = sg.slot or "?"
            gems_str = " + ".join(sg.gems)
            lines.append(f"{marker}[{slot}] {gems_str}")

    # ── Items ──
    uniques = [i for i in build.items if i.rarity == "UNIQUE" and i.name]
    rares = [i for i in build.items if i.rarity == "RARE" and i.name]
    if uniques:
        lines += ["", "## UNIQUE ITEMS"]
        for item in uniques:
            slot = f" ({item.slot})" if item.slot else ""
            lines.append(f"- {item.name}{slot}")
    if rares:
        lines += ["", "## RARE ITEMS"]
        for item in rares:
            slot = f" ({item.slot})" if item.slot else ""
            base = f" [{item.base}]" if item.base else ""
            lines.append(f"- {item.name}{base}{slot}")

    # ── Diagnostics ──
    issues = []
    if s.life < 3000 and s.energy_shield < 3000:
        issues.append(f"VERY LOW EHP ({ehp:,.0f}). Aim for 4000+ life or 6000+ ES.")
    elif s.life < 4000 and s.energy_shield < 2000:
        issues.append(
            f"LOW LIFE ({s.life:,.0f}). Aim for 4500+ for comfortable mapping."
        )
    if s.fire_res < 75 or s.cold_res < 75 or s.lightning_res < 75:
        uncapped = []
        if s.fire_res < 75:
            uncapped.append(f"Fire ({s.fire_res:.0f}%)")
        if s.cold_res < 75:
            uncapped.append(f"Cold ({s.cold_res:.0f}%)")
        if s.lightning_res < 75:
            uncapped.append(f"Lightning ({s.lightning_res:.0f}%)")
        issues.append(
            f"UNCAPPED RESISTS: {', '.join(uncapped)}. Priority fix — will die to ele damage."
        )
    if s.chaos_res < -30:
        issues.append(
            f"CHAOS RES VERY LOW ({s.chaos_res:.0f}%). Dangerous in DoT/poison content."
        )
    if s.hit_chance and s.hit_chance < 90:
        issues.append(
            f"LOW HIT CHANCE ({s.hit_chance:.1f}%). Missing attacks = massive DPS loss."
        )
    if s.total_dps < 50000 and s.total_dot < 50000 and s.level >= 70:
        issues.append("LOW DPS for endgame. Check gem links, support gems, and weapon.")
    if not uniques and s.level >= 60:
        issues.append("No unique items equipped. Consider build-enabling uniques.")

    if issues:
        lines += ["", "## [!] ISSUES FOUND"]
        for i, issue in enumerate(issues, 1):
            lines.append(f"{i}. {issue}")
    else:
        lines += ["", "## STATUS: Build looks solid. No critical issues detected."]

    # ── Notes ──
    if build.notes:
        lines += ["", "## BUILD NOTES", build.notes[:500]]

    return "\n".join(lines)


async def poe_price_check(item_name: str, item_type: str = "") -> str:
    """Check the price of an item on poe.ninja."""
    try:
        ninja = _get_ninja()
        results = await ninja.search_item(item_name, item_type or None)
    except Exception as e:
        return f"Error: {e}"

    if not results:
        return f"No results found for '{item_name}' on poe.ninja."

    lines = [f"Price check: '{item_name}' (league: {ninja.league})", ""]
    for item in results[:10]:
        price_str = f"{item.chaos_value:,.0f}c"
        if item.divine_value and item.divine_value >= 1:
            price_str += f" ({item.divine_value:.1f} div)"
        trend = ""
        if item.change_pct:
            arrow = "+" if item.change_pct > 0 else "-"
            trend = f" {arrow}{abs(item.change_pct):.1f}%"
        listings = f" [{item.listing_count} listings]" if item.listing_count else ""
        lines.append(f"  {item.name}: {price_str}{trend}{listings}")

    return "\n".join(lines)


async def poe_currency_rates() -> str:
    """Get current currency exchange rates in chaos."""
    try:
        ninja = _get_ninja()
        rates = await ninja.get_currency_overview()
    except Exception as e:
        return f"Error: {e}"

    if not rates:
        return "No currency data available."

    lines = [f"Currency rates (league: {ninja.league})", ""]
    for rate in rates[:25]:
        trend = ""
        if rate.change_pct:
            arrow = "+" if rate.change_pct > 0 else "-"
            trend = f" {arrow}{abs(rate.change_pct):.1f}%"
        lines.append(f"  {rate.name}: {rate.chaos_equivalent:,.1f}c{trend}")

    return "\n".join(lines)


async def poe_meta_overview(category: str = "SkillGem") -> str:
    """Get top items/gems by value (proxy for meta popularity)."""
    try:
        ninja = _get_ninja()
        items = await ninja.get_item_overview(category)
    except Exception as e:
        return f"Error: {e}"

    if not items:
        return f"No data for category '{category}'."

    items_sorted = sorted(items, key=lambda i: i.chaos_value, reverse=True)

    lines = [f"Top {category} (league: {ninja.league})", ""]
    for item in items_sorted[:20]:
        price_str = f"{item.chaos_value:,.0f}c"
        if item.divine_value and item.divine_value >= 1:
            price_str += f" ({item.divine_value:.1f} div)"
        lines.append(f"  {item.name}: {price_str}")

    return "\n".join(lines)


async def poe_build_cost(code_or_url: str) -> str:
    """Estimate total cost of a PoB build by pricing all unique items."""
    try:
        build = await decode_build(code_or_url)
    except Exception as e:
        return f"Error parsing build: {e}"

    uniques = [i for i in build.items if i.rarity == "UNIQUE"]
    if not uniques:
        return "No unique items found in this build."

    ninja = _get_ninja()
    lines = [
        f"Build cost estimate: {build.stats.class_name}/{build.stats.ascendancy}",
        "",
    ]
    total_chaos = 0
    not_found = []

    for item in uniques:
        if not item.name:
            continue
        try:
            results = await ninja.search_item(item.name)
            if results:
                price = results[0]
                total_chaos += price.chaos_value
                price_str = f"{price.chaos_value:,.0f}c"
                if price.divine_value and price.divine_value >= 1:
                    price_str += f" ({price.divine_value:.1f} div)"
                lines.append(f"  {item.name}: {price_str}")
            else:
                not_found.append(item.name)
        except Exception as e:
            logger.debug("Price lookup failed for %s: %s", item.name, e)
            not_found.append(item.name)

    lines += ["", f"Total (uniques only): {total_chaos:,.0f}c"]

    # Convert to divine if significant
    try:
        rates = await ninja.get_currency_overview()
        divine_rate = next((r.chaos_equivalent for r in rates if "Divine" in r.name), 0)
        if divine_rate > 0:
            lines.append(f"  ≈ {total_chaos / divine_rate:.1f} Divine Orbs")
    except Exception as e:
        logger.debug("Divine rate fetch failed: %s", e)

    if not_found:
        lines += ["", "Not found on poe.ninja:", *[f"  - {n}" for n in not_found]]

    return "\n".join(lines)


async def poe_search_item(query: str, item_type: str = "") -> str:
    """Search for items by name on poe.ninja."""
    return await poe_price_check(query, item_type)


async def poe_wiki_lookup(query: str) -> str:
    """Look up game data on the PoE Wiki (items, areas, gems)."""
    return await wiki_client.search_wiki(query)


async def poe_league_info(topic: str = "all") -> str:
    """Get knowledge about current league, build archetypes, or game mechanics."""
    topic = topic.lower().strip()
    files_map = {
        "league": "league_mechanics.md",
        "builds": "build_archetypes.md",
        "archetypes": "build_archetypes.md",
        "starters": "build_archetypes.md",
        "mechanics": "league_mechanics.md",
    }

    if topic == "all":
        # Return both
        parts = []
        for fname in ["league_mechanics.md", "build_archetypes.md"]:
            fpath = _KNOWLEDGE_DIR / fname
            if fpath.exists():
                parts.append(fpath.read_text(encoding="utf-8"))
        return "\n\n---\n\n".join(parts) if parts else "No knowledge files found."

    fname = files_map.get(topic)
    if fname:
        fpath = _KNOWLEDGE_DIR / fname
        if fpath.exists():
            return fpath.read_text(encoding="utf-8")
    return f"Unknown topic '{topic}'. Available: league, builds, archetypes, starters, mechanics, all."


async def poe_game_status() -> str:
    """Get current in-game status from the Client.txt monitor."""
    from poe_intel.startup import get_tracker, get_watcher

    tracker = get_tracker()
    if not tracker:
        return "Game monitor is not active. Set poe_client_log and poe_monitor_enabled in config."

    watcher = get_watcher()
    status = tracker.get_status()

    # Add recent events
    if watcher and watcher.recent_events:
        recent = watcher.recent_events[-10:]
        status += "\n\n=== Recent Events ===\n"
        for ev in recent:
            status += (
                f"  [{ev.timestamp}] {ev.event_type}: {ev.data.get('groups', '')}\n"
            )

    return status


async def poe_economy_snapshot() -> str:
    """Get the latest economy snapshot from the background feed (if running)."""
    from poe_intel.feeds.economy_feed import EconomyFeed

    # Try to get the global feed instance
    feed = _get_economy_feed()
    if feed:
        return feed.get_summary()
    # Fallback: just fetch current rates
    return await poe_currency_rates()


# Global economy feed reference (set by main.py startup)
_economy_feed: "EconomyFeed | None" = None


def set_economy_feed(feed):
    global _economy_feed
    _economy_feed = feed


def _get_economy_feed():
    return _economy_feed


async def poe_compare_builds(code1: str, code2: str) -> str:
    """Compare two PoB builds side by side."""
    try:
        b1 = await decode_build(code1)
        b2 = await decode_build(code2)
    except Exception as e:
        return f"Error parsing builds: {e}"

    s1, s2 = b1.stats, b2.stats
    lines = [
        f"Build 1: {s1.class_name}/{s1.ascendancy} Lv.{s1.level}",
        f"Build 2: {s2.class_name}/{s2.ascendancy} Lv.{s2.level}",
        "",
        f"{'Stat':<20} {'Build 1':>12} {'Build 2':>12} {'Diff':>10}",
        "-" * 56,
    ]

    comparisons = [
        ("Total DPS", s1.total_dps, s2.total_dps),
        ("Life", s1.life, s2.life),
        ("Energy Shield", s1.energy_shield, s2.energy_shield),
        ("Armour", s1.armour, s2.armour),
        ("Evasion", s1.evasion, s2.evasion),
        ("Fire Res", s1.fire_res, s2.fire_res),
        ("Cold Res", s1.cold_res, s2.cold_res),
        ("Lightning Res", s1.lightning_res, s2.lightning_res),
        ("Chaos Res", s1.chaos_res, s2.chaos_res),
        ("Block", s1.block_chance, s2.block_chance),
        ("Crit Chance", s1.crit_chance, s2.crit_chance),
    ]

    for label, v1, v2 in comparisons:
        diff = v2 - v1
        if abs(v1) > 1000 or abs(v2) > 1000:
            diff_str = f"{diff:+,.0f}"
            lines.append(f"{label:<20} {v1:>12,.0f} {v2:>12,.0f} {diff_str:>10}")
        else:
            diff_str = f"{diff:+.1f}"
            lines.append(f"{label:<20} {v1:>12.1f} {v2:>12.1f} {diff_str:>10}")

    # Verdict
    lines += ["", "=== VERDICT ==="]
    dps_winner = "Build 1" if s1.total_dps > s2.total_dps else "Build 2"
    ehp1 = s1.life + s1.energy_shield
    ehp2 = s2.life + s2.energy_shield
    tank_winner = "Build 1" if ehp1 > ehp2 else "Build 2"
    lines.append(f"Higher DPS: {dps_winner} ({max(s1.total_dps, s2.total_dps):,.0f})")
    lines.append(f"Tankier (EHP): {tank_winner} ({max(ehp1, ehp2):,.0f})")

    # Check uncapped resists
    for label, b, stats in [("Build 1", b1, s1), ("Build 2", b2, s2)]:
        issues = []
        if stats.fire_res < 75:
            issues.append(f"Fire {stats.fire_res:.0f}%")
        if stats.cold_res < 75:
            issues.append(f"Cold {stats.cold_res:.0f}%")
        if stats.lightning_res < 75:
            issues.append(f"Light {stats.lightning_res:.0f}%")
        if stats.chaos_res < 0:
            issues.append(f"Chaos {stats.chaos_res:.0f}%")
        if issues:
            lines.append(f"{label} WARNINGS: uncapped/low resists: {', '.join(issues)}")

    return "\n".join(lines)


async def poe_character_lookup(account_name: str, character_name: str = "") -> str:
    """Look up a character from the GGG public API."""
    if character_name:
        return await ggg_client.get_character_summary(account_name, character_name)

    # List all characters
    try:
        chars = await ggg_client.get_characters(account_name)
    except Exception as e:
        return f"Error: {e}"

    if not chars:
        return f"No characters found for account '{account_name}' (profile may be private)."

    lines = [f"Characters for {account_name}:", ""]
    for c in chars:
        lines.append(
            f"  {c.get('name', '?')} — {c.get('class', '?')} Lv.{c.get('level', '?')} "
            f"({c.get('league', '?')})"
        )
    return "\n".join(lines)


async def poe_ladder(league: str = "", limit: int = 20) -> str:
    """Get the league ladder (top players)."""
    if not league:
        from config import settings

        league = settings.poe_league

    try:
        data = await ggg_client.get_ladder(league, limit=limit)
    except Exception as e:
        return f"Error fetching ladder for '{league}': {e}"

    entries = data.get("entries", [])
    if not entries:
        return f"No ladder data for '{league}'."

    lines = [f"Ladder: {league} (top {limit})", ""]
    for entry in entries:
        rank = entry.get("rank", "?")
        char = entry.get("character", {})
        account = entry.get("account", {})
        name = char.get("name", "?")
        cls = char.get("class", "?")
        level = char.get("level", "?")
        exp = char.get("experience", 0)
        acc = account.get("name", "?")
        dead = " [DEAD]" if entry.get("dead") else ""
        lines.append(f"  #{rank} {name} ({cls} Lv.{level}){dead} — {acc}")

    return "\n".join(lines)


def get_tool_definitions() -> list[dict]:
    """Return tool definitions for NEXUS registry."""
    return [
        {
            "name": "poe_parse_build",
            "description": (
                "Parse a Path of Building (PoB) code or paste URL. "
                "Returns full build analysis: DPS, defenses, resistances, skills, items. "
                "Accepts: raw PoB code, pastebin.com URL, pobb.in URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code_or_url": {
                        "type": "string",
                        "description": "PoB import code or paste URL (pastebin.com, pobb.in)",
                    },
                },
                "required": ["code_or_url"],
            },
            "func": poe_parse_build,
        },
        {
            "name": "poe_price_check",
            "description": (
                "Check the current price of a Path of Exile item on poe.ninja. "
                "Returns price in chaos/divine, trend, listing count."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "Item name to search (e.g. 'Headhunter', 'Mageblood')",
                    },
                    "item_type": {
                        "type": "string",
                        "description": "Optional item type filter (UniqueWeapon, UniqueArmour, SkillGem, etc.)",
                    },
                },
                "required": ["item_name"],
            },
            "func": poe_price_check,
        },
        {
            "name": "poe_currency_rates",
            "description": (
                "Get current Path of Exile currency exchange rates from poe.ninja. "
                "Shows chaos equivalent for Divine Orb, Exalted, and all currencies."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
            "func": poe_currency_rates,
        },
        {
            "name": "poe_meta_overview",
            "description": (
                "Get top items by category from poe.ninja (meta overview). "
                "Categories: SkillGem, UniqueWeapon, UniqueArmour, DivinationCard, Scarab, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Item category (default: SkillGem). See poe.ninja types.",
                    },
                },
            },
            "func": poe_meta_overview,
        },
        {
            "name": "poe_build_cost",
            "description": (
                "Estimate the total cost of a PoB build by pricing all unique items. "
                "Accepts PoB code or paste URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code_or_url": {
                        "type": "string",
                        "description": "PoB import code or paste URL",
                    },
                },
                "required": ["code_or_url"],
            },
            "func": poe_build_cost,
        },
        {
            "name": "poe_search_item",
            "description": (
                "Search for Path of Exile items by name on poe.ninja. "
                "Returns matching items with prices."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Item name or partial name to search",
                    },
                    "item_type": {
                        "type": "string",
                        "description": "Optional type filter",
                    },
                },
                "required": ["query"],
            },
            "func": poe_search_item,
        },
        {
            "name": "poe_wiki_lookup",
            "description": (
                "Look up Path of Exile game data on the PoE Wiki. "
                "Query items, areas, skill gems. Returns structured wiki data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Item, area, or gem name to look up",
                    },
                },
                "required": ["query"],
            },
            "func": poe_wiki_lookup,
        },
        {
            "name": "poe_league_info",
            "description": (
                "Get knowledge about the current PoE league, build archetypes, "
                "league starters, and game mechanics. "
                "Topics: league, builds, starters, mechanics, all."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic: league, builds, starters, mechanics, all (default: all)",
                    },
                },
            },
            "func": poe_league_info,
        },
        {
            "name": "poe_economy_snapshot",
            "description": (
                "Get the latest economy snapshot with tracked currency and item prices. "
                "Shows trends from the background economy monitor."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
            "func": poe_economy_snapshot,
        },
        {
            "name": "poe_game_status",
            "description": (
                "Get current in-game status from the live Client.txt monitor. "
                "Shows current area, death count, recent events. "
                "Requires poe_monitor_enabled=true and poe_client_log set."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
            "func": poe_game_status,
        },
        {
            "name": "poe_compare_builds",
            "description": (
                "Compare two PoB builds side by side. Shows DPS, defenses, resists "
                "differences and a verdict on which is tankier/higher DPS."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code1": {
                        "type": "string",
                        "description": "First PoB code or paste URL",
                    },
                    "code2": {
                        "type": "string",
                        "description": "Second PoB code or paste URL",
                    },
                },
                "required": ["code1", "code2"],
            },
            "func": poe_compare_builds,
        },
        {
            "name": "poe_character_lookup",
            "description": (
                "Look up a Path of Exile character from the GGG public API. "
                "Shows class, level, league, equipped items. "
                "If no character_name given, lists all characters on the account."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "account_name": {
                        "type": "string",
                        "description": "GGG account name (case-sensitive)",
                    },
                    "character_name": {
                        "type": "string",
                        "description": "Character name (optional — omit to list all)",
                    },
                },
                "required": ["account_name"],
            },
            "func": poe_character_lookup,
        },
        {
            "name": "poe_ladder",
            "description": (
                "Get the league ladder — top players by level/XP. "
                "Shows rank, character name, class, level, account."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "league": {
                        "type": "string",
                        "description": "League name (default: current from config)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of entries (default: 20, max: 200)",
                    },
                },
            },
            "func": poe_ladder,
        },
    ]
