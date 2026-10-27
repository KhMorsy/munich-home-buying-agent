"""The approval gate really stops the agent before it contacts the owner or books a slot.

Uses a scripted fake model (no API key) and the real INTERRUPT_ON / ACTION_TOOLS exports.
"""

from __future__ import annotations

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from deepagents import create_deep_agent

from agent.tools import outreach


class ScriptedModel(GenericFakeChatModel):
    def bind_tools(self, *args, **kwargs):  # the agent binds tools; the script ignores them
        return self


def _tool_call(name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call-{name}"}])


def _agent(script, checkpointer):
    return create_deep_agent(
        model=ScriptedModel(messages=iter(script)),
        tools=outreach.ACTION_TOOLS,
        interrupt_on=outreach.INTERRUPT_ON,
        checkpointer=checkpointer,
    )


def _tool_results(state) -> list[str]:
    return [m.name for m in state.values["messages"] if m.type == "tool"]


def test_owner_message_waits_for_approval_then_sends(monkeypatch):
    sent = []
    monkeypatch.setattr(outreach, "send_message", lambda text, chat_id=None: sent.append(text) or {"message_id": 1})
    agent = _agent(
        [_tool_call("send_owner_message", {"listing_id": "mu-1", "message": "Hi"}), AIMessage(content="done")],
        InMemorySaver(),
    )
    cfg = {"configurable": {"thread_id": "t-owner"}}

    agent.invoke({"messages": [{"role": "user", "content": "contact the owner"}]}, cfg)
    state = agent.get_state(cfg)
    assert state.next, "run should be paused at the approval interrupt"
    assert sent == [] and "send_owner_message" not in _tool_results(state)

    agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), cfg)
    assert len(sent) == 1 and "mu-1" in sent[0]


def test_rejecting_the_booking_never_writes_the_event(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach, "OUTBOX", tmp_path / "outbox")
    slot = outreach._free_slots()[0]["slot_id"]
    agent = _agent(
        [
            _tool_call(
                "create_calendar_event",
                {"listing_id": "mu-1", "listing_title": "Altbau", "address": "Agnesstr. 21", "slot_id": slot},
            ),
            AIMessage(content="ok, not booking"),
        ],
        InMemorySaver(),
    )
    cfg = {"configurable": {"thread_id": "t-cal"}}

    agent.invoke({"messages": [{"role": "user", "content": "book it"}]}, cfg)
    assert agent.get_state(cfg).next
    assert not (tmp_path / "outbox").exists()

    agent.invoke(Command(resume={"decisions": [{"type": "reject", "message": "no"}]}), cfg)
    assert not (tmp_path / "outbox").exists()
