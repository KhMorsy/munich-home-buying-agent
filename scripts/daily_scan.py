#!/usr/bin/env python3
"""Trigger a daily market scan against the local or deployed agent.

Usage:
  # Local (uses the compiled graph in-process)
  python scripts/daily_scan.py

  # Against a deployed LangGraph deployment
  LANGGRAPH_API_URL=https://... LANGGRAPH_ASSISTANT_ID=... python scripts/daily_scan.py --remote
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _local_scan(user_id: str) -> None:
    from agent.graph import agent

    config = {"configurable": {"thread_id": f"daily-scan-{user_id}"}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "daily_scan"}]},
        config=config,
    )
    messages = result.get("messages", [])
    if messages:
        last = messages[-1]
        content = getattr(last, "content", last)
        print(content)
    else:
        print(json.dumps(result, default=str)[:4000])


async def _remote_scan(user_id: str) -> None:
    from langgraph_sdk import get_client

    url = os.environ["LANGGRAPH_API_URL"]
    assistant_id = os.environ["LANGGRAPH_ASSISTANT_ID"]
    client = get_client(url=url)
    thread = await client.threads.create()
    run = await client.runs.wait(
        thread["thread_id"],
        assistant_id,
        input={"messages": [{"role": "user", "content": "daily_scan"}]},
    )
    print(json.dumps(run, default=str)[:4000])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Munich home-buying daily scan")
    parser.add_argument("--remote", action="store_true", help="Call deployed LangGraph API")
    parser.add_argument(
        "--user-id",
        default=os.getenv("DEFAULT_USER_ID", "demo-user"),
        help="Buyer user id (informational for local; profile must already exist)",
    )
    args = parser.parse_args()
    if args.remote:
        asyncio.run(_remote_scan(args.user_id))
    else:
        _local_scan(args.user_id)


if __name__ == "__main__":
    main()
