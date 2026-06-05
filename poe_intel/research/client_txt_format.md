# PoE Client.txt Log File — Research

## File Location (Windows)
- **Steam:** `C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\Client.txt`
- **Standalone:** `C:\Program Files (x86)\Grinding Gear Games\Path of Exile\logs\Client.txt`
- **Epic:** `C:\Program Files\Epic Games\PathOfExile\logs\Client.txt`

## Line Format
```
YYYY/MM/DD HH:MM:SS FRAME_NUM HEX [INFO Client PID] MESSAGE
```

Example:
```
2020/07/25 16:56:25 237826523 b46 [INFO Client 67234] @From wannaBeFamous: Hi, I'd like to buy your 1 Mirror of Kalandra for my 2 Chaos Orb in Harvest
```

### Components
- **Timestamp:** `YYYY/MM/DD HH:MM:SS`
- **Frame number:** integer (monotonic)
- **Hex frame:** hex value
- **Source:** `[INFO Client PID]` where PID is process id
- **Message:** event-specific content

## Event Types & Patterns

### Zone Change (area entered)
```
: You have entered {AREA_NAME}.
```
Regex: `\] : You have entered (.+)\.$`

### Player Death (slain)
```
: {CHARACTER_NAME} has been slain.
```
Regex: `\] : (.+) has been slain\.$`

### Death Count (/deaths command)
```
: You have died {N} time(s).
```
Regex: `\] : You have died (\d+) times?\.$`

### Whisper Received
```
@From {PLAYER}: {MESSAGE}
```
Regex: `\] @From (<.*> )?(.+): (.+)$`
- Group 1: Guild tag (optional)
- Group 2: Player name
- Group 3: Message

### Whisper Sent
```
@To {PLAYER}: {MESSAGE}
```
Regex: `\] @To (<.*> )?(.+): (.+)$`

### Trade Accepted
```
: Trade accepted.
```

### Trade Cancelled
```
: Trade cancelled.
```

### Level Up
```
: {CHARACTER} ({CLASS}) is now level {LEVEL}
```
Regex: `\] : (.+) \((.+)\) is now level (\d+)$`

### Player Joins Area
```
: {PLAYER} has joined the area.
```

### Player Leaves Area
```
: {PLAYER} has left the area.
```

### AFK/DND Toggle
```
: AFK mode is now ON. Autoreply "{MESSAGE}"
: DND mode is now ON. Autoreply "{MESSAGE}"
```

### Chat Message
```
#{CHANNEL} {PLAYER}: {MESSAGE}    (global)
${CHANNEL} {PLAYER}: {MESSAGE}    (trade)
&{CHANNEL} {PLAYER}: {MESSAGE}    (guild)
%{PLAYER}: {MESSAGE}              (party)
```

### Remaining Monsters (/remaining)
```
: {N} monsters remaining.
```

### Server Connection
```
: Connecting to instance server at {IP}:{PORT}
```

### Login
```
: login.pathofexile.com
```

## File Size Considerations
- Client.txt grows indefinitely (can reach 1-2 GB)
- Must use tail-reading (seek to end, read new lines)
- Python approach: `file.seek(0, 2)` on startup, then periodic `readline()`
- Or use `watchdog` / polling with offset tracking

## Base Regex for Line Parsing
```python
import re

LINE_RE = re.compile(
    r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}) \d+ [a-f0-9]+ "
    r"\[INFO Client \d+\] (.+)$"
)
# Group 1: timestamp
# Group 2: message body

EVENT_PATTERNS = {
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
```

## Reference Implementations
- [poe-log-monitor](https://github.com/klayveR/poe-log-monitor) — Node.js, most complete
- [poe-log-events](https://github.com/moepmoep12/poe-log-events) — TypeScript, 18 event types
- [poe-logs-parser](https://github.com/nomis51/poe-logs-parser) — .NET, extensible parser chain
