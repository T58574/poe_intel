"""poe_intel.config — Module-specific configuration.

Reads from environment variables with POE_INTEL_ prefix.
Falls back to sensible defaults for local development.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PoeIntelConfig:
    """Configuration for the poe_intel MCP server."""

    # --- PoB Engine ---
    pob_install_dir: str = field(
        default_factory=lambda: os.getenv(
            "POE_INTEL_POB_DIR",
            "/opt/pob-community"  # Docker default; override for local dev
        )
    )
    pob_lua_binary: str = field(
        default_factory=lambda: os.getenv("POE_INTEL_LUA_BIN", "luajit")
    )
    pob_cache_ttl: int = field(
        default_factory=lambda: int(os.getenv("POE_INTEL_POB_CACHE_TTL", "3600"))
    )

    # --- poe.ninja ---
    ninja_base_url: str = field(
        default_factory=lambda: os.getenv(
            "POE_INTEL_NINJA_URL", "https://poe.ninja/api/data"
        )
    )
    ninja_league: str = field(
        default_factory=lambda: os.getenv("POE_INTEL_NINJA_LEAGUE", "Settlers")
    )
    ninja_cache_ttl: int = field(
        default_factory=lambda: int(os.getenv("POE_INTEL_NINJA_CACHE_TTL", "300"))
    )

    # --- GGG Trade API ---
    trade_base_url: str = field(
        default_factory=lambda: os.getenv(
            "POE_INTEL_TRADE_URL",
            "https://www.pathofexile.com/api/trade"
        )
    )
    trade_user_agent: str = field(
        default_factory=lambda: os.getenv(
            "POE_INTEL_TRADE_UA",
            "NEXUS-PoeIntel/0.1 (contact: nexus@localhost)"
        )
    )
    trade_rate_limit_rps: float = field(
        default_factory=lambda: float(os.getenv("POE_INTEL_TRADE_RPS", "1.0"))
    )

    # --- Client Log Monitor ---
    client_log_path: str = field(
        default_factory=lambda: os.getenv(
            "POE_INTEL_CLIENT_LOG",
            str(Path.home() / "Documents" / "My Games"
                / "Path of Exile" / "logs" / "Client.txt")
        )
    )

    # --- WebSocket ---
    ws_host: str = field(
        default_factory=lambda: os.getenv("POE_INTEL_WS_HOST", "0.0.0.0")
    )
    ws_port: int = field(
        default_factory=lambda: int(os.getenv("POE_INTEL_WS_PORT", "8780"))
    )

    # --- Patch Notes ---
    patch_notes_cache_dir: str = field(
        default_factory=lambda: os.getenv(
            "POE_INTEL_PATCH_CACHE",
            "/tmp/poe_intel/patch_cache"
        )
    )

    # --- General ---
    log_level: str = field(
        default_factory=lambda: os.getenv("POE_INTEL_LOG_LEVEL", "INFO")
    )
    data_dir: str = field(
        default_factory=lambda: os.getenv(
            "POE_INTEL_DATA_DIR",
            str(Path(__file__).parent / "data")
        )
    )

    @property
    def pob_lua_entry(self) -> Path:
        """Path to the PoB Lua headless entry script."""
        return Path(self.pob_install_dir) / "src" / "HeadlessWrapper.lua"

    @property
    def pob_data_dir(self) -> Path:
        """Path to PoB tree/data directory."""
        return Path(self.pob_install_dir) / "TreeData"

    def ensure_dirs(self) -> None:
        """Create required directories if they don't exist."""
        for d in [self.patch_notes_cache_dir, self.data_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)


# Singleton — importable as `from poe_intel.config import cfg`
cfg = PoeIntelConfig()
