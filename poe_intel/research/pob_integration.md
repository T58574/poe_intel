# Path of Building — Integration Research

## Summary
PoB has no official CLI. But there are multiple Python approaches, from zero-dep XML parsing to full Lua recalculation.

## Approach 1: Zero-dependency XML parsing (RECOMMENDED for MVP)

PoB codes are: XML → zlib compress → base64url encode.

```python
import base64, zlib
from xml.etree import ElementTree as ET

def decode_pob(code: str) -> ET.Element:
    xml_bytes = zlib.decompress(base64.urlsafe_b64decode(code))
    return ET.fromstring(xml_bytes)
```

### XML structure
```xml
<PathOfBuilding>
  <Build level="90" className="Witch" ascendClassName="Elementalist">
    <PlayerStat stat="Life" value="6911"/>
    <PlayerStat stat="TotalDPS" value="1234567"/>
    <PlayerStat stat="FireResist" value="75"/>
    <PlayerStat stat="ColdResist" value="75"/>
    <PlayerStat stat="LightningResist" value="75"/>
    <PlayerStat stat="ChaosResist" value="-60"/>
    <!-- 60+ computed stats -->
  </Build>
  <Skills><!-- socket groups with gems --></Skills>
  <Tree><Spec nodes="12345,67890,..."/></Tree>
  <Items><!-- item text blocks --></Items>
  <Config><!-- checkbox states --></Config>
  <Notes>build notes</Notes>
</PathOfBuilding>
```

### Available stats (PlayerStat keys)
| Category | Keys |
|---|---|
| DPS | TotalDPS, TotalDot, BleedDPS, IgniteDPS, PoisonDPS |
| Offense | AverageHit, CritChance, CritMultiplier, HitChance, Speed |
| Life/ES | Life, LifeUnreserved, LifeRegen, EnergyShield, ESRegen |
| Defenses | Armour, Evasion, PhysicalDamageReduction, BlockChance, SpellBlockChance |
| Resists | FireResist, ColdResist, LightningResist, ChaosResist + OverCap variants |
| Attributes | Str, Dex, Int |

**Limitation:** Stats are pre-computed at export time. No recalculation.

## Approach 2: pobapi (PyPI)

```bash
pip install pobapi
```

```python
import pobapi
build = pobapi.from_url("https://pastebin.com/XXXX")
# or: build = pobapi.from_code("eJy...")

build.class_name        # "Witch"
build.ascendancy_name   # "Elementalist"
build.level             # 90
build.stats.total_dps   # float
build.stats.life        # float
build.stats.fire_resistance  # float
build.stats.chaos_resistance # float
```

**Status:** Last release 0.6.0 (~2021). May be stale but functional.
**Deps:** lxml, requests, dataslots, unstdlib

## Approach 3: Headless Lua (full recalc)

### api-stdio branch
Fork: https://github.com/ianderse/PathOfBuilding (branch `api-stdio`)
Requires: LuaJIT installed.

```bash
cd src
POB_API_STDIO=1 luajit HeadlessWrapper.lua
```

JSON-RPC over stdio:
```json
{"action": "load_build_xml", "xml": "<...>"}
{"action": "get_stats"}
{"action": "set_level", "level": 95}
{"action": "quit"}
```

### pob-mcp (Node.js MCP server)
https://github.com/ianderse/pob-mcp — 71 tools, optional Lua bridge.
Could be added to NEXUS MCP registry if needed later.

## Decision: Two-tier approach
1. **MVP:** Zero-dep XML parsing (stdlib only). Covers 90% of use cases.
2. **Future:** api-stdio Lua bridge for live recalculation (when items/tree change).
