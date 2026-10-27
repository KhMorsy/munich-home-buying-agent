#!/usr/bin/env python3
"""Run the LangSmith evals against the agent (Person C).

    python -m evals.run_evals --create-dataset
    python -m evals.run_evals                      # all 5 profiles
    python -m evals.run_evals --limit 1            # smoke test with one profile
    python -m evals.run_evals --live-telegram      # really send the price-drop alert

Needs OPENAI_API_KEY and LANGSMITH_API_KEY. Runs sequentially: scenarios edit the seed file
(restored afterwards) and share the in-memory store.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent.config  # noqa: E402,F401  (loads .env)
from evals.dataset import DATASET_NAME, create_dataset  # noqa: E402
from evals.evaluators import DETERMINISTIC, EVALUATORS, SUMMARY_EVALUATORS  # noqa: E402
from evals.harness import run_scenario  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--create-dataset", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="only the first N examples")
    ap.add_argument("--live-telegram", action="store_true")
    ap.add_argument("--prefix", default="munich-agent")
    ap.add_argument("--repetitions", type=int, default=1, help="repeat each example (LLM runs vary)")
    ap.add_argument("--selftest", action="store_true", help="score synthetic golden/broken runs (no LLM key needed)")
    ap.add_argument("--no-judge", action="store_true", help="skip the LLM-as-judge evaluator")
    args = ap.parse_args()

    if args.create_dataset:
        print(create_dataset())
        return 0

    from langsmith import Client, evaluate

    if not args.selftest and not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set; the agent cannot run. (--selftest needs no LLM key.)")
        return 1

    client = Client()
    data = list(client.list_examples(dataset_name=DATASET_NAME))
    if not data:
        print(f"Dataset {DATASET_NAME!r} not found or empty; run with --create-dataset first.")
        return 1
    if args.limit:
        data = data[: args.limit]

    if args.selftest:
        from evals.fixtures import broken, golden

        for name, target in (("golden", golden), ("broken", broken)):
            r = evaluate(
                target, data=data, evaluators=DETERMINISTIC, summary_evaluators=SUMMARY_EVALUATORS,
                experiment_prefix=f"selftest-{name}", metadata={"synthetic": True, "fixture": name},
                max_concurrency=1, client=client,
            )
            df = r.to_pandas() if hasattr(r, "to_pandas") else None
            print(f"selftest-{name}:", r.experiment_name)
            if df is not None:
                cols = [c for c in df.columns if c.startswith("feedback.")]
                print(df[cols].mean().round(2).to_string())
        return 0

    results = evaluate(
        lambda inputs: run_scenario(inputs, live_telegram=args.live_telegram),
        data=data,
        evaluators=DETERMINISTIC if args.no_judge else EVALUATORS,
        summary_evaluators=SUMMARY_EVALUATORS,
        experiment_prefix=args.prefix,
        num_repetitions=args.repetitions,
        metadata={
            "orch_model": os.getenv("ORCH_MODEL"),
            "sub_model": os.getenv("SUB_MODEL"),
            "telegram": "live" if args.live_telegram else "dry-run",
        },
        max_concurrency=1,
        client=client,
    )
    print(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
