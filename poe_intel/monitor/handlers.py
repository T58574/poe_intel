"""Event handlers for Client.txt events — reactive game assistant."""

import logging
from collections import defaultdict

from poe_intel.monitor.log_watcher import GameEvent

logger = logging.getLogger(__name__)


class GameTracker:
    """Tracks game state from Client.txt events."""

    def __init__(self):
        self.current_area: str = ""
        self.death_count: int = 0
        self.deaths_by_area: dict[str, int] = defaultdict(int)
        self.areas_visited: list[str] = []
        self.character_name: str = ""
        self.character_class: str = ""
        self.character_level: int = 0
        self._alert_callback = None  # async fn(str)

    def set_alert_callback(self, callback):
        self._alert_callback = callback

    async def handle_area_entered(self, event: GameEvent):
        """Track zone changes."""
        area = event.data["groups"][0]
        self.current_area = area
        self.areas_visited.append(area)
        # Keep last 200 areas
        if len(self.areas_visited) > 200:
            self.areas_visited = self.areas_visited[-200:]
        logger.debug("Area entered: %s", area)

    async def handle_death(self, event: GameEvent):
        """Track deaths with area context."""
        char_name = event.data["groups"][0]
        self.character_name = char_name
        self.death_count += 1
        self.deaths_by_area[self.current_area] += 1

        msg = (
            f"[PoE] {char_name} died in {self.current_area or 'unknown area'}. "
            f"Deaths total: {self.death_count}, in this zone: {self.deaths_by_area[self.current_area]}"
        )
        logger.info(msg)

        if self._alert_callback:
            try:
                await self._alert_callback(msg)
            except Exception as e:
                logger.warning("Death alert failed: %s", e)

    async def handle_level_up(self, event: GameEvent):
        """Track level ups."""
        groups = event.data["groups"]
        self.character_name = groups[0]
        self.character_class = groups[1]
        self.character_level = int(groups[2])
        logger.info(
            "Level up: %s (%s) -> %d",
            self.character_name,
            self.character_class,
            self.character_level,
        )

    async def handle_death_count(self, event: GameEvent):
        """Update death count from /deaths command."""
        self.death_count = int(event.data["groups"][0])

    def get_status(self) -> str:
        """Get current tracking status as text."""
        lines = ["=== Game Status ==="]
        if self.character_name:
            lines.append(
                f"Character: {self.character_name} ({self.character_class}) Lv.{self.character_level}"
            )
        if self.current_area:
            lines.append(f"Current area: {self.current_area}")
        lines.append(f"Deaths: {self.death_count}")
        if self.deaths_by_area:
            lines.append("Deaths by area:")
            sorted_areas = sorted(
                self.deaths_by_area.items(), key=lambda x: x[1], reverse=True
            )
            for area, count in sorted_areas[:10]:
                lines.append(f"  {area}: {count}")
        if self.areas_visited:
            lines.append(f"Areas visited: {len(self.areas_visited)}")
        return "\n".join(lines)


def setup_handlers(watcher, tracker: GameTracker):
    """Wire event handlers to the log watcher."""
    watcher.on("area_entered", tracker.handle_area_entered)
    watcher.on("slain", tracker.handle_death)
    watcher.on("level_up", tracker.handle_level_up)
    watcher.on("death_count", tracker.handle_death_count)
