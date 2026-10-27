"""Runtime configuration for the orchestrator and subagents."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

ORCH_MODEL = os.getenv("ORCH_MODEL", "openai:gpt-4.1")
SUB_MODEL = os.getenv("SUB_MODEL", "openai:gpt-4.1-mini")
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "demo-user")

# Soft spend / loop guards (Person C may override via LIMIT_MIDDLEWARE)
TOOL_CALL_LIMIT = int(os.getenv("TOOL_CALL_LIMIT", "40"))
MODEL_CALL_LIMIT = int(os.getenv("MODEL_CALL_LIMIT", "30"))

# Ranking weights (must sum to 1.0)
W_PRICE_VS_MARKET = 0.40
W_AFFORDABILITY = 0.35
W_FIT = 0.25

# Bavarian purchase-cost defaults (also documented for Person B finance tool)
GRUNDERWERBSTEUER = 0.035
NOTARY_PCT = 0.02
MAKLER_PCT = 0.0357

STATUS_PIPELINE = (
    "new",
    "suggested",
    "shortlisted",
    "owner_contacted",
    "viewing_proposed",
    "viewing_booked",
    "rejected",
)
