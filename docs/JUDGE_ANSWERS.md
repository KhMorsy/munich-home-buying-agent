# Judge Q&A — how we handled the hackathon directions

Pitch angles we chose: **Don't forget**, **Act safely**, **New skills**, **Prove it works**.

Use these as spoken answers (30–60 seconds each).

---

## 1. Don't forget — long tasks without losing context or looping

**What we built**
- Short-term: Deep Agents / LangGraph thread state + summarization so the chat does not bloat.
- Long-term: LangGraph Store namespaces outside the prompt:
  - `users` → buyer profile
  - `properties` → every listing with price history, status pipeline, scores, insights
  - `runs` → daily scan digests (cheap weekly/monthly recall)
- Dedup: `get_seen_ids` / `filter_new_listings` — we never re-suggest the same `listing_id` unless the price changed.
- Price memory: `score_and_rank(..., price_updates_json)` appends history, re-ranks, and drafts Telegram alerts like “was #9, now #5”.

**One-liner for judges**  
“The agent can run for days: memory lives in a store, not in the context window, so it remembers every offer, its status, and price changes without looping on the same flats.”

---

## 2. Act safely — human approval (+ spend limits)

**What we built**
- `INTERRUPT_ON` on `send_owner_message` and `create_calendar_event` — Human-in-the-loop must approve before anything leaves the system.
- Owner “email” is a Telegram message to a teammate posing as the owner; calendar booking writes an `.ics` only after approval.
- Soft spend guards: `ToolCallLimitMiddleware` / `ModelCallLimitMiddleware` (plus a hard cap of 5 owner messages per thread).
- Draft-first: `draft_owner_message` shows the text; only then `send_owner_message`.

**Demo line**  
“Watch: contact owner → approval gate → only then the owner’s phone buzzes. Reject once and nothing is sent.”

---

## 3. New skills — reusable skills the agent can call

**What we built** (Person B)
- `agent/skills/mortgage-plan/SKILL.md`
- `agent/skills/renovation-estimate/SKILL.md`
- `agent/skills/negotiation-brief/SKILL.md`
- Three subagents (`financial`, `valuation`, `negotiation`) load those skills and call deterministic tools (`mortgage_plan`, `estimate_valuation`, `find_comparables`).
- The LLM explains; it does **not** invent the mortgage math or ranking weights.

**One-liner**  
“Skills package domain playbooks; tools do the numbers; the orchestrator only composes the story.”

---

## 4. Prove it works — evaluate tool use and steps, not just the answer

**What we built** (Person C)
- LangSmith traces on EU workspace for every run.
- Offline + online evals (`evals/`, `pytest` safety suite):
  - **trajectory** — all three subagents before `score_and_rank`
  - **safety** — owner/calendar tools interrupt; unapproved actions = 0
  - **dedup** — second scan finds no “new” repeats
  - **price_drop** — drop detected, re-rank, `send_telegram`
  - **finance** — monthly payment matches `mortgage_plan` within 1%
- 38 unit tests covering memory ranking, market tools, outreach, and safety gates.

**Show them**  
LangSmith experiment + one trace with an interrupt, and `pytest tests -q` → 38 passed.

---

## Bonus if asked: Cheaper & smarter / More reliable

- **Cheaper:** orchestrator on a strong model (`ORCH_MODEL`), subagents on a mini model (`SUB_MODEL`).
- **Reliable:** deterministic ranking and mortgage code; soft search fallbacks so empty markets still return closest seed matches; Telegram + calendar failures return structured errors instead of crashing the graph.

---

## Architecture in one breath

“Orchestrator interviews and searches → three specialist subagents score each listing → deterministic ranker → Store remembers everything → HITL before outreach → Telegram on price drops → LangSmith evals prove the path, not just the text.”
