#!/usr/bin/env python3
"""Create a daily 08:00 cron on a LangSmith / LangGraph deployment.

Requires:
  LANGGRAPH_API_URL
  LANGGRAPH_ASSISTANT_ID
  optional LANGGRAPH_API_KEY (or LANGSMITH_API_KEY)

Usage:
  python scripts/setup_cron.py
  python scripts/setup_cron.py --schedule "0 8 * * *"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


async def main_async(schedule: str) -> None:
    from langgraph_sdk import get_client

    url = os.getenv("LANGGRAPH_API_URL")
    assistant_id = os.getenv("LANGGRAPH_ASSISTANT_ID")
    if not url or not assistant_id:
        print(
            "Set LANGGRAPH_API_URL and LANGGRAPH_ASSISTANT_ID in .env first.",
            file=sys.stderr,
        )
        sys.exit(1)

    api_key = os.getenv("LANGGRAPH_API_KEY") or os.getenv("LANGSMITH_API_KEY")
    client = get_client(url=url, api_key=api_key)
    cron = await client.crons.create(
        assistant_id,
        schedule=schedule,
        input={"messages": [{"role": "user", "content": "daily_scan"}]},
    )
    print("Cron created:")
    print(cron)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--schedule",
        default="0 8 * * *",
        help="Cron expression (default: daily 08:00 UTC)",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.schedule))


if __name__ == "__main__":
    main()
