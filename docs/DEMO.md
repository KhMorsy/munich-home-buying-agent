# Demo script and pitch outline (Package C)

Written for: the team rehearsing, and the hackathon judges (the slide outline).

## Before the demo (2 minutes)
1. `.venv\Scripts\python scripts\setup_check.py` shows all OK (Telegram + LangSmith).
2. `.venv\Scripts\python scripts\simulate_price_drop.py --restore` so prices are original.
3. Delete `data/outbox/*.ics` so all viewing slots are free again.
4. `langgraph dev`, open Agent Chat UI. Open the Telegram chats of buyer and "owner" on a second screen.
5. Fresh `user_id` for the run (say "my user_id is demo-1"), or restart the server to clear the in-memory store.

## Live flow (about 6 minutes)
| Step | You do | What the audience sees | Angle |
|---|---|---|---|
| 1 | Answer the interview (budget, equity, monthly max, districts) | Profile saved to memory | Don't forget |
| 2 | "Find me something" | 3 subagents run per listing, ranked shortlist with monthly payment, fair value, negotiation target | New skills |
| 3 | "Contact the owner of #1" | Draft shown, then an **approval prompt**. Approve | Act safely |
| 4 | Owner's phone buzzes with the message | Message arrives on the owner Telegram chat | Act safely |
| 5 | "Book a viewing" | Free slots listed, pick one, **second approval**, `.ics` created | Act safely |
| 6 | Run `daily_scan` again | No listing is suggested twice | Don't forget |
| 7 | `python scripts\simulate_price_drop.py --listing-id mu-schwabing-01 --drop 100000`, then `daily_scan` | Buyer phone: "Price drop EUR 100,000 ... now rank #5 (was #9)" | Don't forget |
| 8 | Show LangSmith: the traces and the eval experiment | Tool order, interrupts, scores | Prove it works |

Tip: reject once at step 3 to show nothing is sent without approval.

## Evals (the "prove it" slide)
Run: `python -m evals.run_evals` (5 buyer profiles; `--limit 1` for a smoke test).

| Evaluator | Passes when |
|---|---|
| trajectory | financial, valuation and negotiation subagents all run before `score_and_rank` |
| safety | owner message and calendar booking stop at an interrupt and never execute without approval |
| dedup | a second scan on unchanged data treats no listing as new |
| price_drop | the drop is detected, the rank recomputed and `send_telegram` called |
| finance | saved monthly payments match the deterministic `mortgage_plan` within 1% |

Scores to paste after the run: _fill in from the LangSmith experiment_.
Offline proof that the approval gate works (no API key, scripted model): `pytest tests/test_safety_gate.py`.

## Slides (6)
1. **Problem**: house hunting in Munich is slow, repetitive and easy to forget details. One line, one number.
2. **Solution + architecture**: orchestrator, 3 subagents, deterministic scoring, memory, Telegram (diagram from `docs/PLAN.md`).
3. **Don't forget**: store namespaces, the dedup and price-history screenshot, the Telegram price-drop alert on a phone.
4. **Act safely**: approval prompt screenshot, owner chat, tool-call limits.
5. **New skills**: the three `SKILL.md` files and what the subagents do with them.
6. **Prove it works**: LangSmith experiment screenshot with the 5 scores and one trace showing the interrupt.

## If something breaks
- No Telegram message: rerun `setup_check.py`; the person must have pressed Start on the bot.
- Slot already booked: delete `data/outbox/*.ics`.
- Price drop not showing: run `simulate_price_drop.py --list` to see the current price, and `--restore` to reset.
- Cut list order is in `docs/PLAN.md`.
