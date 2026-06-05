"""poe_intel.models — Pydantic data models for the PoE intelligence module.

All domain types are strictly typed. These models form the data contract
between MCP tools, the WebSocket bridge, and the analytics engine.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class BuildVerdict(str, Enum):
    """Starter Validator output classification."""
    RELIABLE_STARTER = "RELIABLE_STARTER"
    RISKY_STARTER = "RISKY_STARTER"
    AVOID = "AVOID"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class DamageType(str, Enum):
    PHYSICAL = "Physical"
    FIRE = "Fire"
    COLD = "Cold"
    LIGHTNING = "Lightning"
    CHAOS = "Chaos"


class ChangeType(str, Enum):
    BUFF = "buff"
    NERF = "nerf"
    REWORK = "rework"
    NEW = "new"
    REMOVED = "removed"


# ---------------------------------------------------------------------------
# PoB Engine Models
# ---------------------------------------------------------------------------

class PoBMetrics(BaseModel):
    """Core metrics extracted from Path of Building via Lua engine."""
    full_dps: float = Field(0.0, description="Combined DPS (all damage sources)")
    total_ehp: float = Field(0.0, description="Effective Hit Pool")
    max_hit_physical: float = Field(0.0, description="Max physical hit survivable")
    max_hit_elemental: float = Field(0.0, description="Max elemental hit survivable")
    max_hit_chaos: float = Field(0.0, description="Max chaos hit survivable")
    life: int = Field(0, description="Total life pool")
    energy_shield: int = Field(0, description="Total energy shield")
    mana: int = Field(0, description="Total mana")
    evasion: int = Field(0, description="Evasion rating")
    armour: int = Field(0, description="Armour rating")
    block_chance: float = Field(0.0, description="Block chance %")
    spell_block: float = Field(0.0, description="Spell block %")
    dodge_chance: float = Field(0.0, description="Spell suppression %")
    fire_res: int = Field(0, description="Fire resistance %")
    cold_res: int = Field(0, description="Cold resistance %")
    lightning_res: int = Field(0, description="Lightning resistance %")
    chaos_res: int = Field(0, description="Chaos resistance %")
    recovery_rate: float = Field(0.0, description="Life recovery per second")
    cap_check_passed: bool = Field(True, description="All res caps met")
    warnings: list[str] = Field(default_factory=list, description="Cap/build warnings")
    main_skill: str = Field("", description="Primary skill gem name")
    ascendancy: str = Field("", description="Ascendancy class")
    level: int = Field(0, description="Character level")
    raw_xml_hash: str = Field("", description="SHA256 of the build XML for caching")


class PoBResult(BaseModel):
    """Full result of pob_stat_engine tool invocation."""
    success: bool
    source: str = Field("", description="Original source URL or code")
    metrics: Optional[PoBMetrics] = None
    error: Optional[str] = None
    parse_time_ms: float = Field(0.0, description="Lua engine parse duration")


# ---------------------------------------------------------------------------
# Patch Notes Models
# ---------------------------------------------------------------------------

class SkillChange(BaseModel):
    """Single skill/gem change entry from patch notes."""
    skill_name: str
    change_type: ChangeType
    description: str
    numeric_delta: Optional[float] = Field(None, description="% change if quantifiable")
    tags: list[str] = Field(default_factory=list)


class TreeChange(BaseModel):
    """Passive tree change entry."""
    node_name: str
    change_type: ChangeType
    description: str


class MechanicChange(BaseModel):
    """New or modified game mechanic."""
    name: str
    change_type: ChangeType
    description: str
    affected_skills: list[str] = Field(default_factory=list)


class PatchNotes(BaseModel):
    """Structured patch notes for a league version."""
    version: str
    league_name: str = ""
    release_date: Optional[str] = None
    skill_changes: list[SkillChange] = Field(default_factory=list)
    tree_changes: list[TreeChange] = Field(default_factory=list)
    mechanic_changes: list[MechanicChange] = Field(default_factory=list)
    raw_sections: dict[str, str] = Field(
        default_factory=dict,
        description="Raw text sections keyed by header",
    )


# ---------------------------------------------------------------------------
# Market & Economy Models
# ---------------------------------------------------------------------------

class CurrencyRate(BaseModel):
    """Currency exchange rate from poe.ninja."""
    name: str
    chaos_equivalent: float
    icon_url: str = ""
    trend_7d: float = Field(0.0, description="7-day price trend %")


class UniqueItem(BaseModel):
    """Unique item data from poe.ninja."""
    name: str
    base_type: str = ""
    links: int = 0
    chaos_value: float = 0.0
    exalted_value: float = 0.0
    divine_value: float = 0.0
    confidence: str = "low"
    icon_url: str = ""
    listing_count: int = 0


class BuildPopularity(BaseModel):
    """Build popularity entry from poe.ninja."""
    skill: str
    ascendancy: str
    count: int
    percentage: float
    dps_median: float = 0.0


class NinjaResult(BaseModel):
    """Result of query_ninja_api tool invocation."""
    success: bool
    category: str
    league: str = ""
    currency_rates: list[CurrencyRate] = Field(default_factory=list)
    unique_items: list[UniqueItem] = Field(default_factory=list)
    build_stats: list[BuildPopularity] = Field(default_factory=list)
    error: Optional[str] = None


class TradeResult(BaseModel):
    """Result of trade_price_check tool invocation."""
    success: bool
    item_query: dict[str, Any] = Field(default_factory=dict)
    min_price: float = 0.0
    median_price: float = 0.0
    max_price: float = 0.0
    currency: str = "chaos"
    total_listings: int = 0
    results: list[dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Live Monitor Models
# ---------------------------------------------------------------------------

class GameEvent(BaseModel):
    """Parsed event from Client.txt log stream."""
    timestamp: datetime
    event_type: str  # "death", "zone_enter", "trade", "level_up", "whisper", "system"
    zone: str = ""
    details: str = ""
    raw_line: str = ""


class LogStreamResult(BaseModel):
    """Result of stream_client_logs tool invocation."""
    success: bool
    events: list[GameEvent] = Field(default_factory=list)
    lines_read: int = 0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Analytics / Verdict Models
# ---------------------------------------------------------------------------

class StarterVerdict(BaseModel):
    """Starter Validator algorithm output."""
    build_name: str
    verdict: BuildVerdict
    dps_delta_pct: float = Field(0.0, description="DPS change % from 3.27 to 3.28")
    ehp_delta_pct: float = Field(0.0, description="EHP change % from 3.27 to 3.28")
    affected_by: list[SkillChange] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class DeathAnalysis(BaseModel):
    """Efficiency Watchdog death analysis output."""
    zone: str
    damage_type: DamageType
    player_resistance: int
    weakness_detected: str
    recommendation: str
    estimated_cost: str = ""


# ---------------------------------------------------------------------------
# WebSocket Message Envelope
# ---------------------------------------------------------------------------

class WSMessage(BaseModel):
    """WebSocket message envelope for poe_intel events."""
    type: str  # "pob_result", "market_update", "game_event", "verdict", "error"
    namespace: str = "poe_intel"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: dict[str, Any] = Field(default_factory=dict)
