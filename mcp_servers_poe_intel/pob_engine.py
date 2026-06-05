"""poe_intel.pob_engine — PoB Stat Engine with Lua core integration.

This module wraps the Path of Building Community Fork's Lua engine
to extract build metrics (DPS, EHP, resistances, cap checks) from
Pastebin/pobb.in links or raw PoB XML/encoded build codes.

Architecture:
    ┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
    │  MCP Tool   │────▶│  PoBStatEngine   │────▶│  LuaRunner  │
    │ (server.py) │     │  (orchestrator)  │     │  (subprocess)│
    └─────────────┘     └──────────────────┘     └──────────────┘
                              │                        │
                        fetch & decode           luajit HeadlessWrapper.lua
                        build code               ──▶ JSON metrics stdout

Isolation contract:
    - This module NEVER imports from NEXUS core.
    - All interaction with NEXUS happens through the MCP protocol.
    - The Lua subprocess is sandboxed: no network, no write outside /tmp.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
import time
import zlib
from pathlib import Path
from typing import Any, Optional

import httpx

from .config import cfg
from .models import PoBMetrics, PoBResult

logger = logging.getLogger(f"poe_intel.{__name__}")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regex patterns for build code sources
_PASTEBIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?pastebin\.com/(?:raw/)?([a-zA-Z0-9]+)"
)
_POBBIN_RE = re.compile(
    r"(?:https?://)?pobb\.in/([a-zA-Z0-9_-]+)"
)
_POE_NINJA_BUILD_RE = re.compile(
    r"(?:https?://)?poe\.ninja/[^/]+/builds/char/[^?]+\?i=(\d+)"
)
# Base64-like PoB code (starts with specific bytes after decode)
_POB_CODE_RE = re.compile(r"^[A-Za-z0-9+/=_-]{50,}$")

# Lua runner timeout
_LUA_TIMEOUT = 30  # seconds

# In-memory cache: hash -> (PoBMetrics, timestamp)
_metrics_cache: dict[str, tuple[PoBMetrics, float]] = {}


# ---------------------------------------------------------------------------
# Build Code Fetching & Decoding
# ---------------------------------------------------------------------------

async def _fetch_pastebin(code_id: str) -> str:
    """Fetch raw build code from Pastebin."""
    url = f"https://pastebin.com/raw/{code_id}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text.strip()


async def _fetch_pobbin(code_id: str) -> str:
    """Fetch build code from pobb.in."""
    url = f"https://pobb.in/{code_id}/raw"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.text.strip()


def _decode_pob_code(encoded: str) -> str:
    """Decode PoB base64+zlib build string to XML.

    PoB build codes are: base64(zlib_deflate(XML))
    Handles both standard base64 and URL-safe variants.
    """
    # Normalize URL-safe base64
    encoded = encoded.replace("-", "+").replace("_", "/")
    # Add padding if needed
    padding = 4 - (len(encoded) % 4)
    if padding != 4:
        encoded += "=" * padding

    try:
        compressed = base64.b64decode(encoded)
        xml_bytes = zlib.decompress(compressed)
        return xml_bytes.decode("utf-8", errors="replace")
    except (zlib.error, base64.binascii.Error) as e:
        raise ValueError(f"Failed to decode PoB build code: {e}") from e


async def resolve_build_source(source: str) -> str:
    """Resolve a build source (URL or code) to raw PoB XML.

    Accepts:
        - Pastebin URL/ID
        - pobb.in URL/ID
        - Raw PoB encoded build string
        - Raw XML (passthrough)

    Returns:
        PoB XML string.
    """
    source = source.strip()

    # Already XML?
    if source.startswith("<?xml") or source.startswith("<PathOfBuilding"):
        return source

    # Pastebin URL
    m = _PASTEBIN_RE.match(source)
    if m:
        encoded = await _fetch_pastebin(m.group(1))
        return _decode_pob_code(encoded)

    # pobb.in URL
    m = _POBBIN_RE.match(source)
    if m:
        encoded = await _fetch_pobbin(m.group(1))
        return _decode_pob_code(encoded)

    # Raw encoded build code
    if _POB_CODE_RE.match(source) and len(source) > 100:
        return _decode_pob_code(source)

    raise ValueError(
        f"Cannot resolve build source. Expected a Pastebin/pobb.in URL "
        f"or a PoB build code. Got: {source[:80]}..."
    )


# ---------------------------------------------------------------------------
# Lua Engine Interface
# ---------------------------------------------------------------------------

def _build_xml_hash(xml: str) -> str:
    """SHA256 hash of the build XML for caching."""
    return hashlib.sha256(xml.encode("utf-8")).hexdigest()[:16]


def _write_temp_build(xml: str) -> Path:
    """Write build XML to a temp file for the Lua runner."""
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="poe_intel_")) / "build.xml"
    tmp.write_text(xml, encoding="utf-8")
    return tmp


async def _run_lua_engine(build_xml_path: Path) -> dict[str, Any]:
    """Execute the PoB Lua engine in a subprocess and parse JSON output.

    The HeadlessWrapper.lua script loads the build XML, runs the calculation
    engine, and outputs a JSON blob with all computed stats to stdout.

    If LuaJIT/PoB is not installed, falls back to XML-only parsing.
    """
    lua_entry = cfg.pob_lua_entry
    lua_bin = cfg.pob_lua_binary

    if not lua_entry.exists():
        logger.warning(
            "PoB Lua entry not found at %s — falling back to XML parser",
            lua_entry,
        )
        return await _parse_xml_fallback(build_xml_path)

    env = {
        "LUA_PATH": f"{cfg.pob_install_dir}/src/?.lua;{cfg.pob_install_dir}/src/?/init.lua;;",
        "POB_RUNTIME": "headless",
    }

    try:
        proc = await asyncio.create_subprocess_exec(
            lua_bin,
            str(lua_entry),
            str(build_xml_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cfg.pob_install_dir,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_LUA_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.error("Lua engine timed out after %ds", _LUA_TIMEOUT)
        proc.kill()
        return {"error": f"Lua engine timed out after {_LUA_TIMEOUT}s"}
    except FileNotFoundError:
        logger.warning(
            "LuaJIT binary '%s' not found — falling back to XML parser",
            lua_bin,
        )
        return await _parse_xml_fallback(build_xml_path)

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        logger.error("Lua engine exited with code %d: %s", proc.returncode, err)
        return {"error": f"Lua engine error (code {proc.returncode}): {err[:500]}"}

    raw = stdout.decode("utf-8", errors="replace").strip()
    # The Lua wrapper may output non-JSON preamble; find the JSON block
    json_start = raw.find("{")
    json_end = raw.rfind("}") + 1
    if json_start == -1 or json_end == 0:
        logger.error("No JSON found in Lua output: %s", raw[:300])
        return {"error": "Lua engine produced no parseable JSON output"}

    try:
        return json.loads(raw[json_start:json_end])
    except json.JSONDecodeError as e:
        logger.error("JSON parse error from Lua output: %s", e)
        return {"error": f"JSON parse error: {e}"}


async def _parse_xml_fallback(build_xml_path: Path) -> dict[str, Any]:
    """Fallback parser: extract stats directly from PoB XML without Lua.

    This provides approximate values by parsing the XML tree directly.
    Accuracy is lower than the Lua engine but works without LuaJIT.
    """
    import xml.etree.ElementTree as ET

    try:
        tree = ET.parse(build_xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}"}

    stats: dict[str, Any] = {"_fallback": True}

    # Extract Build node attributes
    build_node = root.find("Build")
    if build_node is not None:
        stats["level"] = int(build_node.get("level", "1"))
        stats["className"] = build_node.get("className", "")
        stats["ascendClassName"] = build_node.get("ascendClassName", "")

        # Player stats are in <PlayerStat> children
        for ps in build_node.findall("PlayerStat"):
            stat_name = ps.get("stat", "")
            stat_val = ps.get("value", "0")
            try:
                stats[stat_name] = float(stat_val)
            except ValueError:
                stats[stat_name] = stat_val

    # Extract main skill
    skills_node = root.find("Skills")
    if skills_node is not None:
        for skill_set in skills_node.findall("Skill"):
            if skill_set.get("mainActiveSkill"):
                # Find the main gem
                for gem in skill_set.findall("Gem"):
                    if gem.get("nameSpec"):
                        stats["mainSkill"] = gem.get("nameSpec", "")
                        break
                break

    return stats


# ---------------------------------------------------------------------------
# Metrics Extraction
# ---------------------------------------------------------------------------

def _lua_output_to_metrics(raw: dict[str, Any], xml_hash: str) -> PoBMetrics:
    """Convert Lua engine JSON output to PoBMetrics model."""
    if raw.get("_fallback"):
        return _xml_stats_to_metrics(raw, xml_hash)

    warnings: list[str] = []

    # Resistance cap checks
    fire_res = int(raw.get("FireResist", raw.get("fire_res", 0)))
    cold_res = int(raw.get("ColdResist", raw.get("cold_res", 0)))
    light_res = int(raw.get("LightningResist", raw.get("lightning_res", 0)))
    chaos_res = int(raw.get("ChaosResist", raw.get("chaos_res", 0)))

    cap_ok = True
    for name, val, cap in [
        ("Fire", fire_res, 75),
        ("Cold", cold_res, 75),
        ("Lightning", light_res, 75),
        ("Chaos", chaos_res, -60),  # Chaos has no hard cap requirement
    ]:
        if name != "Chaos" and val < cap:
            warnings.append(f"{name} Res uncapped: {val}% (need {cap}%)")
            cap_ok = False
        elif name == "Chaos" and val < 0:
            warnings.append(f"Negative Chaos Res: {val}%")

    return PoBMetrics(
        full_dps=float(raw.get("CombinedDPS", raw.get("TotalDPS", 0))),
        total_ehp=float(raw.get("TotalEHP", 0)),
        max_hit_physical=float(raw.get("PhysicalMaximumHitTaken", 0)),
        max_hit_elemental=float(raw.get("ElementalMaximumHitTaken", 0)),
        max_hit_chaos=float(raw.get("ChaosMaximumHitTaken", 0)),
        life=int(raw.get("Life", 0)),
        energy_shield=int(raw.get("EnergyShield", 0)),
        mana=int(raw.get("Mana", 0)),
        evasion=int(raw.get("Evasion", 0)),
        armour=int(raw.get("Armour", 0)),
        block_chance=float(raw.get("BlockChance", 0)),
        spell_block=float(raw.get("SpellBlockChance", 0)),
        dodge_chance=float(raw.get("SpellSuppressionChance", 0)),
        fire_res=fire_res,
        cold_res=cold_res,
        lightning_res=light_res,
        chaos_res=chaos_res,
        recovery_rate=float(raw.get("LifeRegen", 0)),
        cap_check_passed=cap_ok,
        warnings=warnings,
        main_skill=str(raw.get("MainSkill", raw.get("mainSkill", ""))),
        ascendancy=str(raw.get("AscendClassName", raw.get("ascendClassName", ""))),
        level=int(raw.get("Level", raw.get("level", 0))),
        raw_xml_hash=xml_hash,
    )


def _xml_stats_to_metrics(stats: dict[str, Any], xml_hash: str) -> PoBMetrics:
    """Convert XML-fallback stats dict to PoBMetrics (lower accuracy)."""
    warnings = ["Using XML fallback parser — DPS values may be inaccurate"]

    fire_res = int(stats.get("FireResist", 0))
    cold_res = int(stats.get("ColdResist", 0))
    light_res = int(stats.get("LightningResist", 0))
    chaos_res = int(stats.get("ChaosResist", 0))

    cap_ok = all(r >= 75 for r in [fire_res, cold_res, light_res])

    return PoBMetrics(
        full_dps=float(stats.get("CombinedDPS", stats.get("TotalDPS", 0))),
        total_ehp=float(stats.get("TotalEHP", 0)),
        life=int(stats.get("Life", 0)),
        energy_shield=int(stats.get("EnergyShield", 0)),
        mana=int(stats.get("Mana", 0)),
        evasion=int(stats.get("Evasion", 0)),
        armour=int(stats.get("Armour", 0)),
        fire_res=fire_res,
        cold_res=cold_res,
        lightning_res=light_res,
        chaos_res=chaos_res,
        recovery_rate=float(stats.get("LifeRegen", 0)),
        cap_check_passed=cap_ok,
        warnings=warnings,
        main_skill=str(stats.get("mainSkill", "")),
        ascendancy=str(stats.get("ascendClassName", "")),
        level=int(stats.get("level", 0)),
        raw_xml_hash=xml_hash,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class PoBStatEngine:
    """Orchestrates build code resolution, Lua execution, and metric extraction.

    Usage:
        engine = PoBStatEngine()
        result = await engine.analyze("https://pastebin.com/ABC123")
    """

    def __init__(self) -> None:
        self._cache = _metrics_cache
        self._cache_ttl = cfg.pob_cache_ttl

    async def analyze(self, source: str) -> PoBResult:
        """Full analysis pipeline: resolve → decode → Lua engine → metrics.

        Args:
            source: Pastebin URL, pobb.in URL, or raw PoB build code.

        Returns:
            PoBResult with success flag and metrics or error.
        """
        t0 = time.monotonic()

        try:
            xml = await resolve_build_source(source)
        except (ValueError, httpx.HTTPError) as e:
            return PoBResult(
                success=False,
                source=source,
                error=f"Failed to resolve build source: {e}",
            )

        xml_hash = _build_xml_hash(xml)

        # Check cache
        if xml_hash in self._cache:
            metrics, cached_at = self._cache[xml_hash]
            if time.monotonic() - cached_at < self._cache_ttl:
                logger.debug("Cache hit for build %s", xml_hash)
                return PoBResult(
                    success=True,
                    source=source,
                    metrics=metrics,
                    parse_time_ms=0.0,
                )

        # Write XML to temp file and run Lua engine
        build_path = _write_temp_build(xml)
        try:
            raw_output = await _run_lua_engine(build_path)
        finally:
            # Clean up temp files
            try:
                build_path.unlink(missing_ok=True)
                build_path.parent.rmdir()
            except OSError:
                pass

        if "error" in raw_output:
            return PoBResult(
                success=False,
                source=source,
                error=raw_output["error"],
                parse_time_ms=(time.monotonic() - t0) * 1000,
            )

        metrics = _lua_output_to_metrics(raw_output, xml_hash)

        # Cache result
        self._cache[xml_hash] = (metrics, time.monotonic())

        return PoBResult(
            success=True,
            source=source,
            metrics=metrics,
            parse_time_ms=(time.monotonic() - t0) * 1000,
        )

    def invalidate_cache(self, xml_hash: Optional[str] = None) -> int:
        """Invalidate cache. If xml_hash is None, clear all."""
        if xml_hash:
            removed = 1 if self._cache.pop(xml_hash, None) else 0
        else:
            removed = len(self._cache)
            self._cache.clear()
        return removed
