"""PoB code decoder — zero dependencies beyond stdlib.

Decodes Path of Building export codes into structured build data.
Supports: raw PoB codes, pastebin.com URLs, pobb.in URLs.
"""

import base64
import logging
import re
import zlib
from xml.etree import ElementTree as ET

import httpx

from poe_intel.models import BuildItem, BuildStats, ParsedBuild, SkillGroup

logger = logging.getLogger(__name__)

# Stat name mapping: PoB internal → BuildStats field
_STAT_MAP: dict[str, str] = {
    "Life": "life",
    "LifeUnreserved": "life_unreserved",
    "LifeRegen": "life_regen",
    "EnergyShield": "energy_shield",
    "EnergyShieldRegen": "es_regen",
    "Mana": "mana",
    "ManaUnreserved": "mana_unreserved",
    "ManaRegen": "mana_regen",
    "TotalDPS": "total_dps",
    "TotalDot": "total_dot",
    "BleedDPS": "bleed_dps",
    "IgniteDPS": "ignite_dps",
    "PoisonDPS": "poison_dps",
    "AverageHit": "average_hit",
    "CritChance": "crit_chance",
    "CritMultiplier": "crit_multiplier",
    "HitChance": "hit_chance",
    "Speed": "attack_speed",
    "CastSpeed": "cast_speed",
    "Armour": "armour",
    "Evasion": "evasion",
    "PhysicalDamageReduction": "phys_damage_reduction",
    "BlockChance": "block_chance",
    "SpellBlockChance": "spell_block",
    "FireResist": "fire_res",
    "ColdResist": "cold_res",
    "LightningResist": "lightning_res",
    "ChaosResist": "chaos_res",
    "Str": "strength",
    "Dex": "dexterity",
    "Int": "intelligence",
}

_PASTEBIN_RE = re.compile(r"pastebin\.com/(?:raw/)?(\w+)")
_POBBIN_RE = re.compile(r"pobb\.in/(?:u/)?([A-Za-z0-9_-]+)")
# PoB codes are base64 zlib — start with eN/eJ (x\x9c compressed) and are long
_POB_CODE_RE = re.compile(r"[eE][NnJj][A-Za-z0-9+/=_-]{50,}")


def _decode_raw(code: str) -> bytes:
    """Decode a raw PoB code string to XML bytes."""
    code = code.strip()
    # Fix URL-safe base64 padding
    padding = 4 - len(code) % 4
    if padding != 4:
        code += "=" * padding
    raw = base64.urlsafe_b64decode(code)
    return zlib.decompress(raw)


def _extract_pob_from_html(html: str) -> str:
    """Extract PoB import code from HTML page (pobb.in, etc.)."""
    matches = _POB_CODE_RE.findall(html)
    if matches:
        return max(matches, key=len)
    raise ValueError(
        "Could not extract PoB code from page. "
        "Try pasting the raw PoB import code directly (starts with eN...)."
    )


async def _fetch_code_from_url(url: str) -> str:
    """Resolve a paste URL to a raw PoB code string."""
    m_pastebin = _PASTEBIN_RE.search(url)
    m_pobbin = _POBBIN_RE.search(url)

    # Reject guide sites that don't contain PoB codes
    if "maxroll.gg" in url or "poebuilds.cc" in url or "mobalytics.gg" in url:
        raise ValueError(
            "Guide URLs (maxroll, mobalytics) don't contain PoB import codes. "
            "Open the guide, find the PoB code or pobb.in link, and paste that."
        )

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        if m_pastebin:
            paste_id = m_pastebin.group(1)
            resp = await client.get(f"https://pastebin.com/raw/{paste_id}")
            resp.raise_for_status()
            return resp.text.strip()
        elif m_pobbin:
            paste_id = m_pobbin.group(1)
            # pobb.in: fetch page HTML and extract PoB code from it
            resp = await client.get(f"https://pobb.in/{paste_id}")
            resp.raise_for_status()
            body = resp.text.strip()
            # If response looks like raw PoB code, use directly
            if body.startswith("eN") or body.startswith("eJ"):
                return body
            # Otherwise extract from HTML
            return _extract_pob_from_html(body)
        else:
            # Try as direct URL
            resp = await client.get(url)
            resp.raise_for_status()
            body = resp.text.strip()
            if body.startswith("eN") or body.startswith("eJ"):
                return body
            return _extract_pob_from_html(body)


def _parse_xml(xml_bytes: bytes) -> ParsedBuild:
    """Parse PoB XML into a ParsedBuild."""
    root = ET.fromstring(xml_bytes)
    build_el = root.find("Build")
    if build_el is None:
        raise ValueError("Invalid PoB XML: no <Build> element")

    # Basic info
    stats = BuildStats(
        class_name=build_el.get("className", ""),
        ascendancy=build_el.get("ascendClassName", ""),
        level=int(build_el.get("level", "0")),
        bandit=build_el.get("bandit", ""),
    )

    # PlayerStat entries
    for ps in build_el.findall("PlayerStat"):
        stat_name = ps.get("stat", "")
        try:
            value = float(ps.get("value", "0"))
        except (ValueError, TypeError):
            value = 0
        stats.raw_stats[stat_name] = value
        field_name = _STAT_MAP.get(stat_name)
        if field_name and hasattr(stats, field_name):
            setattr(stats, field_name, value)

    # Skills
    skills_el = root.find("Skills")
    skill_groups: list[SkillGroup] = []
    main_group = build_el.get("mainSocketGroup", "1")
    if skills_el is not None:
        for idx, sg in enumerate(skills_el.findall("Skill"), 1):
            gems = []
            for gem in sg.findall("Gem"):
                name = gem.get("nameSpec") or gem.get("skillId", "")
                if name:
                    gems.append(name)
            if gems:
                skill_groups.append(
                    SkillGroup(
                        slot=sg.get("slot", ""),
                        gems=gems,
                        is_enabled=sg.get("enabled", "true") == "true",
                        is_main=(str(idx) == main_group),
                    )
                )

    # Items
    items_el = root.find("Items")
    items: list[BuildItem] = []
    if items_el is not None:
        for item_el in items_el.findall("Item"):
            raw = (item_el.text or "").strip()
            if not raw:
                continue
            lines = raw.split("\n")
            rarity = ""
            name = ""
            base = ""
            for line in lines:
                if line.startswith("Rarity:"):
                    rarity = line.split(":", 1)[1].strip()
                elif rarity and not name:
                    name = line.strip()
                elif rarity and name and not base:
                    base = line.strip()
            items.append(
                BuildItem(
                    name=name,
                    base=base,
                    rarity=rarity,
                    raw_text=raw,
                )
            )

        # Map slots from ItemSet
        for item_set in items_el.findall("ItemSet"):
            for slot_el in item_set.findall("Slot"):
                slot_name = slot_el.get("name", "")
                item_id = slot_el.get("itemId", "")
                if item_id and item_id.isdigit():
                    idx = int(item_id) - 1
                    if 0 <= idx < len(items):
                        items[idx].slot = slot_name

    # Tree nodes
    tree_nodes: list[int] = []
    tree_el = root.find("Tree")
    if tree_el is not None:
        for spec in tree_el.findall("Spec"):
            nodes_str = spec.get("nodes", "")
            if nodes_str:
                for n in nodes_str.split(","):
                    n = n.strip()
                    if n.isdigit():
                        tree_nodes.append(int(n))
            break  # Only first spec (active)

    # Notes
    notes_el = root.find("Notes")
    notes = (notes_el.text or "").strip() if notes_el is not None else ""

    return ParsedBuild(
        stats=stats,
        skills=skill_groups,
        items=items,
        tree_nodes=tree_nodes,
        notes=notes,
        raw_xml=xml_bytes.decode("utf-8", errors="replace"),
    )


async def decode_build(code_or_url: str) -> ParsedBuild:
    """Decode a PoB code or paste URL into a ParsedBuild.

    Accepts:
    - Raw PoB code (base64 string starting with eN...)
    - pastebin.com/XXXX or pastebin.com/raw/XXXX
    - pobb.in/XXXX
    """
    code_or_url = code_or_url.strip()

    # URL → fetch raw code first
    if code_or_url.startswith("http"):
        code_or_url = await _fetch_code_from_url(code_or_url)

    xml_bytes = _decode_raw(code_or_url)
    return _parse_xml(xml_bytes)
