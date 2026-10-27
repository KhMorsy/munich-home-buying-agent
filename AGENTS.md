# Instructions for coding agents

- Read `docs/PLAN.md` before making changes. It is the source of truth for the architecture, memory design, ranking and data contracts.
- The human you are working with owns one work package (A, B or C, see `README.md`). Ask which one if it is unclear, and only edit files owned by that package.
- Code against the shared contracts in `agent/schemas.py`. Do not change them without the team agreeing.
- Only package A edits `agent/graph.py`. Packages B and C expose their pieces through the exports named in `README.md`.
- Keep tools deterministic where the plan says so (`mortgage_plan`, `score_and_rank`, price-change detection). The LLM explains the results; it does not calculate them.
- Every tool that contacts a person or books something must stay behind human approval (`INTERRUPT_ON`).
- Python 3.11+. Secrets come from `.env` and must never be committed.
- Time budget is about 2 hours total: prefer the simplest working version, and follow the cut list in `docs/PLAN.md` if behind.
