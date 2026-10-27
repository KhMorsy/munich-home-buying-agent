---
name: negotiation-brief
description: Prepare a negotiation brief for a Munich listing - comparable sales, a target price, the maximum discount to ask for and concrete arguments. Use before contacting an owner or when the buyer asks what to offer.
---

# Negotiation brief

Use `find_comparables(listing_json)`. It returns the comps, a deterministic `target_price`,
the `max_discount_pct` and the base arguments.

## How the target is set
- Comp value = fair value (from comps) - renovation cost.
- Target = comp value, but always between 3% below asking (a polite, credible ask even for bargains)
  and 12% below asking (anything lower is not taken seriously in Munich).

## Writing the brief
1. Keep the tool's `target_price` and `max_discount_pct` unchanged.
2. You may rephrase or reorder `arguments`, and add at most two more taken *only* from the listing description
   (for example no elevator, a busy road, or rented out). Never invent facts.
3. Order the arguments strongest first: comps, then renovation, then condition and location, then speed and certainty.
4. Tone with private owners in Munich: factual and friendly, not lowball theatre. Lead with the comps.

## Output
Return the `NegotiationResult` JSON.
