# GGG Official API & Patch Notes — Research

## Official API
**Docs:** https://www.pathofexile.com/developer/docs
**Reference:** https://www.pathofexile.com/developer/docs/reference

### Public (no auth)
- `GET /api/leagues[/{id}]`
- `GET /api/ladders/{id}`
- `GET /api/public-stash-tabs[?id={change_id}]`
- `GET /api/trade/data/*` (items, stats, static, leagues)
- `GET /api/streams`

### Session-based (POESESSID cookie)
- `GET /character-window/get-characters`
- `GET /character-window/get-items`
- `GET /character-window/get-passive-skills`
- `GET /character-window/get-stash-items`

### OAuth 2.1 required
- `GET /api/character[/{name}]`
- `GET /api/stash/{league}[/{stash_id}]`
- `POST /api/trade/search/{league}`
- `GET /api/trade/fetch/{items}`
- `GET /api/profile`

**User-Agent:** `OAuth {clientId}/{version} (contact: {contact})`
**Rate limits:** Dynamic via response headers (`X-Rate-Limit-*`). ~4 req/s safe.

## Patch Notes — NO API
**There is no structured API for patch notes.**

### Sources
1. **Forum:** `pathofexile.com/forum/view-forum/patch-notes` — HTML, returns 403 to bots
2. **poewiki.net Cargo API:** `versions` table — release dates + version numbers only, no text
3. **poepatchnotes.com** — aggregator, no API
4. **Steam events API** — summaries only

### Best approach for patch notes
1. **Manual:** Save patch notes text to local file at league start → LLM parses
2. **Semi-auto:** poewiki.net `cargoquery?tables=versions` for detection + forum scrape with POESESSID
3. **poewiki.net** for game data (items, mods, areas, skills) via Cargo tables

## poewiki.net Cargo API
```
https://www.poewiki.net/w/api.php?action=cargoquery&tables={TABLE}&fields={FIELDS}&where={FILTER}&format=json
```

### Key tables
- `versions` — version, release_date
- `items` — all items with stats
- `skill_levels` — skill gem data per level
- `areas` — zone data (maps, acts)
- `mods` — item modifiers

### Example: get versions
```
GET /w/api.php?action=cargoquery&tables=versions&fields=version,release_date&order_by=release_date+DESC&limit=10&format=json
```

## Game Data (structured, no scraping)
- **RePoE:** https://github.com/brather1ng/RePoE — JSON dumps (gems, mods, base_items, stats, etc.)
- **pypoe-json:** https://github.com/erosson/pypoe-json — auto-updated from Steam depot
- **PyPoE:** https://github.com/Project-Path-of-Exile-Wiki/PyPoE — parses .dat files from GGPK

## Trade API
```
POST /api/trade/search/{league}  → returns { "id": "...", "result": ["hash1", "hash2", ...] }
GET  /api/trade/fetch/{hash1,hash2,...}  → returns item details
```
Rate headers: `X-Rate-Limit-Client: 10:5:10` (requests:window:timeout)
