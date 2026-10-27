"""Deep Agent entrypoint. Only Person A edits this file.

Person B exports SUBAGENTS from agent.subagents.
Person C exports ACTION_TOOLS, INTERRUPT_ON, LIMIT_MIDDLEWARE from agent.tools.outreach.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore

from agent.config import DEFAULT_USER_ID, LANGSMITH_ENDPOINT, ORCH_MODEL
from agent.prompts import ORCHESTRATOR_PROMPT
from agent.tools.memory import MEMORY_TOOLS
from agent.tools.ranking import RANKING_TOOLS

logger = logging.getLogger(__name__)
logger.info("LangSmith endpoint: %s", LANGSMITH_ENDPOINT)

# Allow module import / Studio graph load before .env is filled in.
if not os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "sk-placeholder-set-OPENAI_API_KEY-in-dotenv"
    logger.warning("OPENAI_API_KEY missing; using placeholder so the graph can load.")

# --- Person B (market) + Person C (actions) imports ---
# B is on main; C may still be landing. Keep try/except so Studio never hard-crashes.

try:
    from agent.subagents import SUBAGENTS
except Exception as exc:  # noqa: BLE001
    logger.warning("Person B subagents not available yet: %s", exc)
    SUBAGENTS = []

try:
    from agent.tools.listings import search_listings

    LISTING_TOOLS = [search_listings]
except Exception as exc:  # noqa: BLE001
    logger.warning("Person B search_listings not available yet: %s", exc)
    LISTING_TOOLS = []

try:
    from agent.tools.notify import send_telegram  # type: ignore

    NOTIFY_TOOLS = [send_telegram]
except Exception as exc:  # noqa: BLE001
    logger.warning("Person C send_telegram not available yet: %s", exc)
    NOTIFY_TOOLS = []

try:
    from agent.tools.outreach import (  # type: ignore
        ACTION_TOOLS,
        INTERRUPT_ON,
        LIMIT_MIDDLEWARE,
    )
except Exception as exc:  # noqa: BLE001
    logger.warning("Person C outreach exports not available yet: %s", exc)
    ACTION_TOOLS = []
    INTERRUPT_ON = {
        "send_owner_message": True,
        "create_calendar_event": True,
    }
    LIMIT_MIDDLEWARE = []


def _skills_paths() -> list[str] | None:
    """Skills are Person B's. Wire them if the directory exists."""
    skills_dir = Path(__file__).resolve().parent / "skills"
    if skills_dir.is_dir() and any(skills_dir.glob("*/SKILL.md")):
        # Paths are backend-relative; we mount project skills under /skills/
        return ["/skills/"]
    return None


def _build_backend():
    routes: dict = {
        "/memories/": StoreBackend(namespace=lambda _rt: ("memories",)),
    }
    skills_dir = Path(__file__).resolve().parent / "skills"
    if skills_dir.is_dir() and any(skills_dir.glob("*/SKILL.md")):
        routes["/skills/"] = FilesystemBackend(root_dir=str(skills_dir), virtual_mode=True)
    return CompositeBackend(default=StateBackend(), routes=routes)


# Local / Studio: InMemoryStore. On LangSmith Deployment, omit store= to use
# the platform store, or set LANGGRAPH_STORE accordingly.
_store = InMemoryStore()

_tools = [
    *MEMORY_TOOLS,
    *RANKING_TOOLS,
    *LISTING_TOOLS,
    *NOTIFY_TOOLS,
    *ACTION_TOOLS,
]

_skills = _skills_paths()
_tool_names = {getattr(t, "name", None) for t in _tools}
_interrupt_on = {
    name: cfg
    for name, cfg in (INTERRUPT_ON or {}).items()
    if name in _tool_names
} or None

agent = create_deep_agent(
    model=ORCH_MODEL,
    tools=_tools,
    system_prompt=ORCHESTRATOR_PROMPT
    + f"\n\nDefault user_id for this deployment: `{DEFAULT_USER_ID}`.\n",
    subagents=SUBAGENTS or None,
    interrupt_on=_interrupt_on,
    middleware=list(LIMIT_MIDDLEWARE) if LIMIT_MIDDLEWARE else (),
    backend=_build_backend(),
    store=_store,
    skills=_skills,
    name="munich-home-buying-agent",
)

# langgraph.json expects `agent`
__all__ = ["agent"]
