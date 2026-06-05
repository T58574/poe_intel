# poe.ninja API — Research

## Status
Public API, no auth, no keys. Community-documented (reverse-engineered).

## Base URL
```
https://poe.ninja/api/data/
```

## Endpoints (all GET)

### Currency
```
GET /api/data/currencyoverview?league={LEAGUE}&type=Currency
GET /api/data/currencyoverview?league={LEAGUE}&type=Fragment
```

### Items
```
GET /api/data/itemoverview?league={LEAGUE}&type={TYPE}
```

**Valid types:**
```
Oil, Incubator, Scarab, Fossil, Resonator, Essence,
DivinationCard, Prophecy, SkillGem, BaseType,
HelmetEnchant, UniqueMap, Map, UniqueJewel, UniqueFlask,
UniqueWeapon, UniqueArmour, UniqueAccessory, Beast,
Vial, DeliriumOrb, Omen, UniqueRelic, ClusterJewel,
BlightedMap, BlightRavagedMap, Invitation, Memory,
Coffin, AllflameEmber
```

### League parameter
Case-sensitive. For 3.28: `Mirage` (or `Hardcore Mirage`).
Fallback: `Standard`.

## Rate Limits
**12 requests per 5-minute window** (2.4 req/min).
No per-IP headers. Must implement local throttle.

Recommended cache TTLs:
- Prices: 1 hour
- Sparklines: 30 days
- Display: 10 minutes

## Response: currencyoverview
```json
{
  "lines": [
    {
      "currencyTypeName": "Mirror of Kalandra",
      "chaosEquivalent": 143915.04,
      "pay": { "value": 0.0000070301, "count": 59, "listing_count": 252 },
      "receive": { "value": 146900, "count": 33, "listing_count": 161 },
      "paySparkLine": { "data": [...], "totalChange": -2.5 },
      "receiveSparkLine": { "data": [...], "totalChange": 1.1 },
      "detailsId": "mirror-of-kalandra"
    }
  ],
  "currencyDetails": [
    { "id": 22, "icon": "...", "name": "Mirror of Kalandra", "tradeId": "mirror" }
  ]
}
```

## Response: itemoverview
```json
{
  "lines": [
    {
      "id": 12345,
      "name": "Headhunter",
      "icon": "...",
      "chaosValue": 28000.0,
      "exaltedValue": 17.5,
      "divineValue": 140.0,
      "listingCount": 47,
      "sparkline": { "data": [...], "totalChange": -3.2 },
      "detailsId": "headhunter"
    }
  ]
}
```

### SkillGem extra fields
- `variant` — e.g. "20/20"
- `gemLevel`, `gemQuality` — int
- `corrupted` — bool

## NOT Available via API
- Build aggregates / popularity stats (web UI only)
- Passive tree heatmaps
- Historical data beyond sparklines
- Per-character data

## Documentation sources
- https://github.com/5k-mirrors/misc-poe-tools/blob/master/doc/poe-ninja-api.md
- https://github.com/ayberkgezer/poe.ninja-API-Document
- https://github.com/Davenads/poeninjaAPI-2025
