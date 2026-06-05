# POE Intel — Module Documentation

> AI-friendly reference for developing, extending, and debugging the PoE Intel module.
> Read this before modifying any `poe_intel/` code.

## Architecture

```
poe_intel/
  __init__.py             — Module docstring only
  models.py               — 6 dataclasses (BuildStats, SkillGroup, BuildItem, ParsedBuild, PriceInfo, CurrencyRate)
  tools.py                — 13 LLM tool functions + get_tool_definitions() registry
  startup.py              — init_poe_intel() / shutdown_poe_intel(), wired in main.py
  clients/
    ninja_client.py       — poe.ninja API (rate limiter, cache, Standard fallback)
    pob_decoder.py        — PoB code decoder (base64 → zlib → XML → BuildStats)
    wiki_client.py        — poewiki.net Cargo API (areas, items, gems, versions)
    ggg_client.py         — GGG public API (characters, items, passives, ladder, leagues)
  feeds/
    economy_feed.py       — Background hourly poll of poe.ninja, trend alerts (>15%)
  monitor/
    log_watcher.py        — Async Client.txt tail reader, 12 event patterns, callbacks
    handlers.py           — GameTracker: death/zone/level tracking, alert dispatch
  knowledge/
    build_archetypes.md   — Starter/mid/endgame build reference (LLM knowledge)
    league_mechanics.md   — Current league info (manually updated each league)
  research/               — 5 research docs (read-only reference, not loaded at runtime)
```

## Data Flow

```
User asks PoE question in NEXUS chat
  → Orchestrator selects tools based on LLM request
  → LLM calls poe_* tools (tools.py functions)
    → tools.py delegates to clients/ (ninja, pob, wiki, ggg)
    → clients/ fetch external APIs with rate limiting + caching
    → tools.py formats results as plain text for LLM
  → LLM reasons about results and responds to user

Background:
  startup.py → EconomyFeed.start() → polls poe.ninja hourly
    → stores snapshots in _history dict
    → alerts via callback if price change > 15%
    → optionally persists to FactStore

  startup.py → LogWatcher.start() → tails Client.txt
    → parses lines with regex → GameEvent objects
    → dispatches to GameTracker handlers
    → death events → alert callback
```

## Integration Points with NEXUS

| What | Where | How |
|---|---|---|
| **Tools** | `tools/registry.py:register_all_tools()` | `from poe_intel import tools as poe_tools` in modules list |
| **Tool group** | `tools/registry.py:_TOOL_GROUPS["poe"]` | Set of 13 tool names, toggle in Web UI |
| **Config** | `config.py:Settings` | 5 fields: `poe_league`, `poe_client_log`, `poe_ninja_cache_ttl`, `poe_monitor_enabled`, `poe_character_name` |
| **Persona** | `data/agents.yaml:poe_expert` | T1 persona with PoE tools + web_search |
| **Startup** | `main.py` line ~330 | `init_poe_intel(fact_store, alert_callback)` |
| **Shutdown** | `main.py` finally block | `shutdown_poe_intel()` |
| **REST API** | `interfaces/api/poe_intel.py` | 8 endpoints under `/api/poe/*` |
| **API registration** | `interfaces/web_server.py` | `register_poe_intel_routes(app, auth_dep)` |
| **Web UI** | `web/modules/poe-dashboard.js` | Hub card "PoE Dashboard", 6 tabs |
| **CSS** | `web/css/components/poe-dashboard.css` | `.poe-*` selectors |
| **Hub entry** | `web/modules/hub.js:HUB_CATEGORIES` | Category "PoE Intel" |
| **Hash route** | `web/modules/app.js:SECTION_TO_SCREEN` | `poe → { screen: 'hub', hint: 'poe' }` |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/poe/status` | Module status: league, feed/monitor active, game state |
| GET | `/api/poe/economy/currency` | Currency rates from poe.ninja |
| GET | `/api/poe/economy/items/{type}` | Item prices by type (UniqueWeapon, SkillGem, etc.) |
| GET | `/api/poe/economy/snapshot` | Economy feed tracked items with trends |
| POST | `/api/poe/build/parse` | Parse PoB code → structured JSON |
| GET | `/api/poe/monitor/events` | Recent Client.txt events |
| GET | `/api/poe/ladder/{league}` | League ladder proxy (avoids CORS) |
| GET | `/api/poe/character/{account}` | Character list/items proxy |

## LLM Tools (13)

| Tool | Input | Output | External API |
|---|---|---|---|
| `poe_parse_build` | PoB code/URL | Full build analysis text | pastebin/pobb.in |
| `poe_price_check` | item name | Price + trend + listings | poe.ninja |
| `poe_currency_rates` | — | Top 25 currency rates | poe.ninja |
| `poe_meta_overview` | category | Top items by value | poe.ninja |
| `poe_build_cost` | PoB code/URL | Total unique item costs | poe.ninja |
| `poe_search_item` | query | Matching items + prices | poe.ninja |
| `poe_wiki_lookup` | query | Wiki data (items, gems, areas) | poewiki.net |
| `poe_league_info` | topic | Knowledge base content | local .md files |
| `poe_economy_snapshot` | — | Feed tracked prices | in-memory feed |
| `poe_game_status` | — | Client.txt monitor state | local file |
| `poe_compare_builds` | code1, code2 | Side-by-side comparison | pastebin/pobb.in |
| `poe_character_lookup` | account, char? | Character info + items | GGG API |
| `poe_ladder` | league?, limit? | Top players by level | GGG API |

## How to Add a New PoE Tool

1. **Write the async function** in `poe_intel/tools.py`:
   ```python
   async def poe_my_tool(param: str) -> str:
       """Description for docstring."""
       # Use existing clients
       ninja = _get_ninja()
       result = await ninja.search_item(param)
       # Format as plain text (LLM reads this)
       return "\n".join([...])
   ```

2. **Add tool definition** to `get_tool_definitions()` in the same file:
   ```python
   {
       "name": "poe_my_tool",
       "description": "What this tool does, when to use it.",
       "parameters": {
           "type": "object",
           "properties": { "param": { "type": "string", "description": "..." } },
           "required": ["param"],
       },
       "func": poe_my_tool,
   },
   ```

3. **Add to registry group** in `tools/registry.py:_TOOL_GROUPS["poe"]`:
   ```python
   "poe": { ..., "poe_my_tool" },
   ```

4. **Add to persona** (optional) in `data/agents.yaml:poe_expert.tools`:
   ```yaml
   tools: [..., poe_my_tool, ...]
   ```

## How to Add a New API Client

1. Create `poe_intel/clients/my_client.py`:
   ```python
   """My API client — description."""
   import httpx

   async def get_data(param: str) -> dict:
       async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
           resp = await client.get(URL, params={...})
           resp.raise_for_status()
           return resp.json()
   ```

2. Import in `poe_intel/tools.py`:
   ```python
   from poe_intel.clients import my_client
   ```

3. Use in tool functions. The client handles its own caching/rate-limiting.

## How to Add a New Knowledge File

1. Create `poe_intel/knowledge/my_topic.md` — plain Markdown, LLM-friendly
2. Add mapping in `poe_league_info()` function in `tools.py`:
   ```python
   files_map = { ..., "my_topic": "my_topic.md" }
   ```
3. File is returned as-is to the LLM when requested

## External API Rate Limits

| API | Limit | Cache TTL | Notes |
|---|---|---|---|
| poe.ninja | 12 req / 5 min | 1h (configurable) | Fallback to Standard if league empty |
| poewiki.net | ~1 req/s (convention) | 24h | Cargo query API, no auth |
| GGG public | ~4 req/s | none | Characters may be private (403) |
| GGG trade | dynamic (headers) | — | Not used yet (future) |
| pastebin.com | unspecified | none | For PoB code fetch |

## Config (.env)

```
POE_LEAGUE=Mirage
POE_CLIENT_LOG=C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\Client.txt
POE_NINJA_CACHE_TTL=3600
POE_MONITOR_ENABLED=false
POE_CHARACTER_NAME=
```

## Testing

```bash
# Verify all imports
python -c "from poe_intel.tools import get_tool_definitions; print(len(get_tool_definitions()), 'tools')"

# Test poe.ninja (live)
python -c "import asyncio; from poe_intel.tools import poe_currency_rates; print(asyncio.run(poe_currency_rates()))"

# Test PoB decoder (live)
python -c "import asyncio; from poe_intel.tools import poe_parse_build; print(asyncio.run(poe_parse_build('https://pastebin.com/bQRjfedq')))"

# Test log parser (offline)
python -c "from poe_intel.monitor.log_watcher import parse_line; print(parse_line('2026/03/06 20:15:33 123 b46 [INFO Client 1] : You have entered The Blood Aqueduct.'))"
```

## Known Limitations

- PoB stats are **pre-computed at export time** — no live recalculation without Lua engine
- poe.ninja **has no build/popularity API** — only economy data
- GGG characters may be **private** (return 403)
- Client.txt **grows indefinitely** — watcher seeks to end on startup, doesn't read history
- Patch notes **have no API** — must be manually imported to knowledge/ files
- Wiki Cargo keys have **spaces not underscores** (e.g., `"required level"` not `"required_level"`)
