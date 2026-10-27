---
name: mortgage-plan
description: Build a German (Bavarian) mortgage plan for a Munich property - purchase side costs, loan amount, monthly annuity payment and affordability. Use when asked whether a buyer can afford a listing or what it costs per month.
---

# Mortgage plan (Bavaria)

Never calculate the numbers yourself. Use the tools; your job is to explain the result.

## Steps
1. Get the current rate with `get_mortgage_rates` (10-year fixed, % p.a.).
2. Call `mortgage_plan(listing_id, price, equity, monthly_max, rate, years=30)`.
   - If the listing needs renovation and the buyer wants to finance it, pass `renovation_cost`.
   - Pass `include_makler=false` only if the listing is sold directly by the owner without an agent.
3. Return the `FinanceResult` JSON unchanged, then add one or two plain-language sentences.

## What the numbers mean
- **Side costs (Kaufnebenkosten)**: Grunderwerbsteuer 3.5% (Bavaria), notary + land registry about 2%, Makler 3.57% if an agent is involved. Together about 9.07% of the price.
- **Loan amount** = price + side costs (+ financed renovation) - equity.
- **Monthly payment**: constant annuity (interest + repayment) over `years`.
- **Affordable** means the monthly payment is at or below the buyer's maximum.

## Rules of thumb to mention when relevant
- German banks expect equity to cover at least the side costs; less equity means a higher rate.
- Loan-to-price above 90% usually adds a rate surcharge of 0.2-0.5 points.
- A rate change of 0.5 points moves the payment on a EUR 600k loan by about EUR 170/month.
