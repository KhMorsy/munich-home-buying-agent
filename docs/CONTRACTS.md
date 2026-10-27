# Shared contracts (Person A)

Source of truth: [`agent/schemas.py`](../agent/schemas.py).

## Models
- `Listing` — market listing card
- `FinanceResult` — mortgage plan output (Person B)
- `ValuationResult` — fair value + renovation (Person B)
- `NegotiationResult` — comps + target (Person B)
- `UserProfile` / `PropertyRecord` / `ScoreBreakdown` / `RunLog` / `PriceChange` — memory + ranking (Person A)

## Exports for merge (minute 55)
| Owner | Module | Export |
|---|---|---|
| B | `agent/subagents.py` | `SUBAGENTS` |
| B | `agent/tools/listings.py` | `search_listings` |
| C | `agent/tools/notify.py` | `send_telegram` |
| C | `agent/tools/outreach.py` | `ACTION_TOOLS`, `INTERRUPT_ON`, `LIMIT_MIDDLEWARE` |

Person A wires them in `agent/graph.py` with try/import fallbacks so Studio boots before B/C land.
