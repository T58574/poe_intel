"""poe_intel — PoE Tactical Intelligence MCP Server for NEXUS.

Namespace: poe_intel
Isolation: Fully autonomous module. NEXUS provides only transport (LLM, WebSocket, Auth).
All PoE domain logic lives exclusively in this package.

Modules:
    server      - FastMCP entry point exposing all tools
    pob_engine  - PoB stat engine (Lua core wrapper for DPS/EHP/caps extraction)
    scrapers    - Patch notes parser, poe.ninja integration
    market      - Trade API price checker
    monitor     - Client.txt log streamer
    ws_bridge   - WebSocket bridge for real-time data push to UI
    models      - Pydantic data models (build stats, market data, events)
    config      - Module-specific configuration
"""

__version__ = "0.1.0"
__namespace__ = "poe_intel"
