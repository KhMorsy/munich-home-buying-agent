# Munich Home-Buying Agent

LangChain x Data Reply Hackathon, Munich. A long-running agent that interviews a home buyer, searches the Munich market, evaluates every listing with finance, valuation and negotiation subagents, ranks them, remembers everything it has already suggested, asks for approval before contacting owners or booking viewings, and pings Telegram on price drops.

Stack: LangChain Deep Agents (`create_deep_agent`), OpenAI models, LangGraph Store for long-term memory, LangSmith (tracing, evals, deployment, cron), Tavily for search, Telegram Bot API.

The full plan, including architecture, memory design and ranking, is in [docs/PLAN.md](docs/PLAN.md).

## Hackathon angles
- **Don't forget**: long-term memory outside the context (seen listings, price history, status pipeline, insights)
- **Act safely**: human approval before messaging owners or booking calendar slots, plus tool and model call limits
- **New skills**: `SKILL.md` skills for the mortgage plan, renovation estimate and negotiation brief
- **Prove it works**: LangSmith evals on the agent's steps (tool order, approvals, dedup, price drop) and on the finance numbers

## Work packages

| Person | GitHub | Package | Owns |
|---|---|---|---|
| A | [@KhMorsy](https://github.com/KhMorsy) | Brain and Memory | `pyproject.toml`, `langgraph.json`, `.env.example`, `agent/config.py`, `agent/schemas.py`, `agent/graph.py`, `agent/prompts.py` (orchestrator), `agent/tools/memory.py`, `agent/tools/ranking.py`, `scripts/daily_scan.py`, `scripts/setup_cron.py`, deployment |
| B | [@shima78](https://github.com/shima78) | Market Intelligence | `data/seed_listings.json`, `data/seed_sold_history.json`, `agent/tools/listings.py`, `agent/tools/finance.py`, `agent/tools/comps.py`, `agent/subagents.py`, `agent/skills/*` |
| C | [@justKMM](https://github.com/justKMM) | Actions, Safety and Proof | Telegram + LangSmith setup, `agent/tools/notify.py`, `agent/tools/outreach.py`, `data/mock_calendar.json`, `scripts/simulate_price_drop.py`, `evals/*`, demo script and pitch |

Only Person A (@KhMorsy) edits `agent/graph.py`. B (@shima78) exports `SUBAGENTS` from `agent/subagents.py`. C (@justKMM) exports `ACTION_TOOLS`, `INTERRUPT_ON` and `LIMIT_MIDDLEWARE` from `agent/tools/outreach.py`. A imports them at the merge point.

## Timeline (minutes from kickoff)
- **0-15**: A pushes the scaffold and `agent/schemas.py`. B starts the seed data. C sets up the Telegram bot and LangSmith.
- **15-55**: everyone builds their own package in parallel. Quick check-in at minute 35.
- **55-60**: merge. A wires the exports into `graph.py`.
- **60-80**: end-to-end run in Agent Chat UI.
- **80-100**: A deploys and sets the cron. B polishes the prompts. C runs the evals.
- **100-120**: demo and pitch rehearsal.

## Git workflow
- Pull often: `git pull --rebase` before every push.
- Only touch the files you own. If you need a change in someone else's file, tell them.
- Small commits, prefixed with your package: `[A] memory tools`, `[B] finance tool`, `[C] telegram notify`.
- Never commit `.env`.

## Local run (Person A scaffold)
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env   # fill OPENAI_API_KEY (and later Tavily / Telegram / LangSmith)
langgraph dev          # Studio + Agent Chat UI
pytest tests/test_ranking.py -q
```

Shared schemas for B/C: [`agent/schemas.py`](agent/schemas.py) and [`docs/CONTRACTS.md`](docs/CONTRACTS.md).

## LangSmith (EU workspace)
This hackathon project uses the **EU** host. Set in `.env`:
```
LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
LANGCHAIN_ENDPOINT=https://eu.api.smith.langchain.com
```
`agent/config.py` forces the EU endpoint even if a US URL is pasted by mistake.

## What’s already wired on `main`
| Package | Status |
|---|---|
| **A** Brain/memory/orchestrator | Wired |
| **B** Market intelligence | Wired into `agent/graph.py` (`SUBAGENTS`, `search_listings`, skills) |
| **C** Telegram / outreach / evals | Not on `main` yet |
