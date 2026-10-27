---
name: renovation-estimate
description: Estimate the fair value and renovation cost of a Munich listing from recent comparable sales and the listing's condition. Use when valuing a property or judging whether it is over- or underpriced.
---

# Renovation estimate and valuation

Use `estimate_valuation(listing_json)`. It is deterministic: do not change its numbers.

## How the tool decides
| Condition | condition_score | Renovation EUR/m² |
|---|---|---|
| new | 0.95 | 0 |
| renovated | 0.90 | 0 |
| good | 0.75 | 0 |
| dated (cosmetic: floors, paint, kitchen) | 0.55 | 350 |
| needs_renovation (bathroom, electrics, windows, heating) | 0.30 | 900 |
| unknown | 0.60 | 150 |

- **Fair value** is the value in good condition: median EUR/m² of the closest same-district sales, times the size,
  with +8% for new builds (2015 or later), +3% for renovated, +5% for flats under 45 m², and -5% for flats over 110 m².
- The ranking compares *asking + renovation* against fair value, so renovation is never counted twice.

## Read the description for hidden condition
If the listing text contradicts its `condition` field (for example "original bathroom", "single-glazed",
"old electrics", "damp" or "gas heating per flat"), set `condition` to `needs_renovation` in the listing JSON
before calling the tool, and say so in the summary.

## Output
Return the `ValuationResult` JSON. Flag it in one sentence if the asking price is more than 8% above fair value
(overpriced) or more than 5% below (possible bargain, so check why).
