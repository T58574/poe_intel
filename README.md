# ⚔️ PoE Intel — Model Context Protocol (MCP) Server & Path of Exile Intelligence Suite

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/Protocol-Model_Context_Protocol_(MCP)-8A2BE2?style=flat-square)](https://modelcontextprotocol.io/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![poe.ninja](https://img.shields.io/badge/Economy-poe.ninja_API-FF6B6B?style=flat-square)](https://poe.ninja/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

**An intelligent Path of Exile telemetry suite and MCP server empowering AI coding assistants (Claude, Cursor, Antigravity) with live economy rates, PoB build decoding, wiki querying, and real-time game log tracking.**

[Key Features](#-key-features) • [Architecture](#-architecture) • [MCP Tools Registry](#-mcp-tools-registry) • [Quick Start](#-quick-start) • [License](#-license)

</div>

---

## 📖 Overview

**PoE Intel** is a specialized Model Context Protocol (MCP) server and automation engine designed to connect Large Language Models directly to Path of Exile's game ecosystem. It gives AI agents the ability to decode raw Path of Building (PoB) share links on the fly, analyze item modifiers, query live `poe.ninja` exchange rates, search `poewiki.net` Cargo tables, and monitor local `Client.txt` logs for in-game death and zone events.

Whether used as a background desktop agent or plugged into Claude Desktop / Cursor IDE, PoE Intel enables instant, data-backed theorycrafting and game analysis.

---

## ✨ Key Features

- 🛠️ **13 Model Context Protocol (MCP) Tools**
  - Exposes standardized tool functions for item lookups, currency conversion rates, passive skill searches, and character inspection over standard JSON-RPC (stdio / SSE).
- 📊 **Real-Time Economy Feed (`poe.ninja`)**
  - Automated background price poller tracking Divine/Chaos ratios, scarabs, div cards, and unique item valuations with alert callbacks on market surges (>15%).
- 🧬 **Instant Path of Building (PoB) Decoder**
  - Decodes base64-compressed zlib PoB strings into structured Python dataclasses (`BuildStats`, `SkillGroup`, `BuildItem`, `EffectiveHP`, `DPS`).
- 📜 **Client.txt Real-Time Log Monitor**
  - Non-blocking asynchronous log tailer parsing 12 distinct in-game event patterns (zone transitions, player deaths, level ups, trade whispers).
- 📚 **Integrated Cargo Wiki Engine (`poewiki.net`)**
  - Directly queries mediawiki Cargo tables for precise gem scaling stats, unique item drop sources, and historical league modifiers.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│              LLM Client (Claude / Cursor / Antigravity)          │
└─────────────────────────────────┬────────────────────────────────┘
                                  │ MCP Protocol (JSON-RPC stdio)
┌─────────────────────────────────▼────────────────────────────────┐
│                       PoE Intel MCP Server                       │
│                                                                  │
│  ┌────────────────────────┐  ┌────────────────────────────────┐  │
│  │ 13 MCP Tool Handlers   │  │ PoB Base64/XML Decoder         │  │
│  └────────────────────────┘  └────────────────────────────────┘  │
│  ┌────────────────────────┐  ┌────────────────────────────────┐  │
│  │ poe.ninja Price Cache  │  │ Client.txt Async Log Watcher   │  │
│  └────────────────────────┘  └────────────────────────────────┘  │
└─────────────────────────────────┬────────────────────────────────┘
                                  │ External APIs & Local Game Logs
┌─────────────────────────────────▼────────────────────────────────┐
│      poe.ninja API • GGG Public API • poewiki.net • Client.txt   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ MCP Tools Registry

| Tool Name | Description | Parameters |
|---|---|---|
| `poe_get_currency_rate` | Get live Divine/Chaos ratio and currency exchange rates | `league: string, currency: string` |
| `poe_lookup_item` | Query live item price and market volume on poe.ninja | `league: string, item_name: string` |
| `poe_decode_pob` | Decode raw PoB string/pobb.in into structured stats | `pob_code: string` |
| `poe_search_wiki` | Search poewiki.net Cargo database for item/gem data | `query: string, category: string` |
| `poe_get_character` | Fetch character equipment and passive tree from GGG API | `account_name: string, character: string` |
| `poe_get_active_events` | Read recent death, zone, and level events from log | `limit: int` |

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone https://github.com/T58574/poe_intel.git
cd poe_intel
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run Standalone MCP Server
```bash
python -m poe_intel.startup
```

### 3. Connect to Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "poe-intel": {
      "command": "python",
      "args": ["-m", "mcp_servers_poe_intel.pob_engine"],
      "cwd": "C:/path/to/poe_intel"
    }
  }
}
```

---

## 📜 License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.
