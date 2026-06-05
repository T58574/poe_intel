"""POE Intel data models."""

from dataclasses import dataclass, field


@dataclass
class BuildStats:
    """Parsed PoB build statistics."""

    class_name: str = ""
    ascendancy: str = ""
    level: int = 0
    bandit: str = ""

    # Offense
    total_dps: float = 0
    total_dot: float = 0
    bleed_dps: float = 0
    ignite_dps: float = 0
    poison_dps: float = 0
    average_hit: float = 0
    crit_chance: float = 0
    crit_multiplier: float = 0
    hit_chance: float = 0
    attack_speed: float = 0
    cast_speed: float = 0

    # Life / ES / Mana
    life: float = 0
    life_unreserved: float = 0
    life_regen: float = 0
    energy_shield: float = 0
    es_regen: float = 0
    mana: float = 0
    mana_unreserved: float = 0
    mana_regen: float = 0

    # Defenses
    armour: float = 0
    evasion: float = 0
    phys_damage_reduction: float = 0
    block_chance: float = 0
    spell_block: float = 0

    # Resistances
    fire_res: float = 0
    cold_res: float = 0
    lightning_res: float = 0
    chaos_res: float = 0

    # Attributes
    strength: float = 0
    dexterity: float = 0
    intelligence: float = 0

    # All raw PlayerStat entries
    raw_stats: dict = field(default_factory=dict)


@dataclass
class SkillGroup:
    """A socket group from the build."""

    slot: str = ""
    gems: list[str] = field(default_factory=list)
    is_enabled: bool = True
    is_main: bool = False


@dataclass
class BuildItem:
    """An equipped item from the build."""

    name: str = ""
    base: str = ""
    rarity: str = ""
    slot: str = ""
    raw_text: str = ""


@dataclass
class ParsedBuild:
    """Full parsed PoB build."""

    stats: BuildStats = field(default_factory=BuildStats)
    skills: list[SkillGroup] = field(default_factory=list)
    items: list[BuildItem] = field(default_factory=list)
    tree_nodes: list[int] = field(default_factory=list)
    notes: str = ""
    raw_xml: str = ""


@dataclass
class PriceInfo:
    """Price data from poe.ninja."""

    name: str = ""
    chaos_value: float = 0
    divine_value: float = 0
    exalted_value: float = 0
    listing_count: int = 0
    change_pct: float = 0  # sparkline totalChange
    icon: str = ""
    details_id: str = ""


@dataclass
class CurrencyRate:
    """Currency exchange rate."""

    name: str = ""
    chaos_equivalent: float = 0
    change_pct: float = 0
    icon: str = ""
