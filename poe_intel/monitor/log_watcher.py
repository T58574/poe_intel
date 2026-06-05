"""Client.txt async log watcher — tail-reads new lines and emits events.

PoE writes to Client.txt in real-time. This watcher seeks to end on startup,
then polls for new lines periodically.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Awaitable

from utils.async_utils import safe_bg

logger = logging.getLogger(__name__)

# Base regex: extract timestamp and message body from log line
_LINE_RE = re.compile(
    r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) \d+ [a-f0-9]+ "
    r"\[INFO Client \d+\] (.+)$"
)

# Event patterns applied to the message body
_EVENT_PATTERNS: dict[str, re.Pattern] = {
    "area_entered": re.compile(r"^: You have entered (.+)\.$"),
    "slain": re.compile(r"^: (.+) has been slain\.$"),
    "death_count": re.compile(r"^: You have died (\d+) times?\.$"),
    "level_up": re.compile(r"^: (.+) \((.+)\) is now level (\d+)$"),
    "whisper_from": re.compile(r"^@From (<.+?> )?(.+?): (.+)$"),
    "whisper_to": re.compile(r"^@To (<.+?> )?(.+?): (.+)$"),
    "trade_accepted": re.compile(r"^: Trade accepted\.$"),
    "trade_cancelled": re.compile(r"^: Trade cancelled\.$"),
    "player_joined": re.compile(r"^: (.+) has joined the area\.$"),
    "player_left": re.compile(r"^: (.+) has left the area\.$"),
    "remaining": re.compile(r"^: (\d+) monsters remaining\.$"),
    "connecting": re.compile(r"^: Connecting to instance server at (.+)$"),
}


@dataclass
class GameEvent:
    """A parsed game event from Client.txt."""

    timestamp: str
    event_type: str
    data: dict = field(default_factory=dict)
    raw_line: str = ""


# Callback type for event handlers
EventCallback = Callable[[GameEvent], Awaitable[None]]


def parse_line(line: str) -> GameEvent | None:
    """Parse a single log line into a GameEvent, or None if unparseable."""
    line = line.strip()
    if not line:
        return None

    m = _LINE_RE.match(line)
    if not m:
        return None

    timestamp, body = m.group(1), m.group(2)

    for event_type, pattern in _EVENT_PATTERNS.items():
        em = pattern.match(body)
        if em:
            return GameEvent(
                timestamp=timestamp,
                event_type=event_type,
                data={"groups": em.groups()},
                raw_line=line,
            )

    return None


class LogWatcher:
    """Async Client.txt watcher with event callbacks."""

    def __init__(self, log_path: str, poll_interval: float = 0.5):
        self.log_path = Path(log_path)
        self.poll_interval = poll_interval
        self._callbacks: dict[str, list[EventCallback]] = {}
        self._global_callbacks: list[EventCallback] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._recent_events: list[GameEvent] = []
        self._max_recent = 100

    def on(self, event_type: str, callback: EventCallback):
        """Register a callback for a specific event type."""
        self._callbacks.setdefault(event_type, []).append(callback)

    def on_any(self, callback: EventCallback):
        """Register a callback for all events."""
        self._global_callbacks.append(callback)

    @property
    def recent_events(self) -> list[GameEvent]:
        return list(self._recent_events)

    async def start(self):
        """Start watching the log file."""
        if self._running:
            return
        if not self.log_path.exists():
            logger.warning("Client.txt not found: %s", self.log_path)
            return
        self._running = True
        self._task = safe_bg(self._watch_loop(), "poe_log_watcher")
        logger.info("LogWatcher started: %s", self.log_path)

    async def stop(self):
        """Stop watching."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("LogWatcher stopped")

    async def _watch_loop(self):
        """Main watch loop — seek to end, then read new lines."""
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                # Seek to end — we only care about new events
                f.seek(0, 2)
                logger.debug("Seeked to end of Client.txt (pos %d)", f.tell())

                while self._running:
                    line = f.readline()
                    if line:
                        event = parse_line(line)
                        if event:
                            await self._dispatch(event)
                    else:
                        await asyncio.sleep(self.poll_interval)
        except Exception as e:
            logger.error("LogWatcher error: %s", e)
            self._running = False

    async def _dispatch(self, event: GameEvent):
        """Dispatch event to registered callbacks."""
        self._recent_events.append(event)
        if len(self._recent_events) > self._max_recent:
            self._recent_events = self._recent_events[-self._max_recent :]

        # Type-specific callbacks
        for cb in self._callbacks.get(event.event_type, []):
            try:
                await cb(event)
            except Exception as e:
                logger.error("Event callback error (%s): %s", event.event_type, e)

        # Global callbacks
        for cb in self._global_callbacks:
            try:
                await cb(event)
            except Exception as e:
                logger.error("Global event callback error: %s", e)
