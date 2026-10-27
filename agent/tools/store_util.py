"""Shared LangGraph Store access with an in-memory fallback for local/tests."""

from __future__ import annotations

from typing import Any

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

_FALLBACK_STORE = InMemoryStore()


def get_agent_store() -> BaseStore:
    """Return the active LangGraph store, or a process-local fallback."""
    try:
        from langgraph.config import get_store

        store = get_store()
        if store is not None:
            return store
    except Exception:
        pass
    return _FALLBACK_STORE


def reset_fallback_store() -> InMemoryStore:
    """Replace the fallback store (for unit tests)."""
    global _FALLBACK_STORE
    _FALLBACK_STORE = InMemoryStore()
    return _FALLBACK_STORE


def put_json(store: BaseStore, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None:
    store.put(namespace, key, value)


def get_json(store: BaseStore, namespace: tuple[str, ...], key: str) -> dict[str, Any] | None:
    item = store.get(namespace, key)
    if item is None:
        return None
    return item.value  # type: ignore[return-value]


def list_json(store: BaseStore, namespace: tuple[str, ...]) -> list[tuple[str, dict[str, Any]]]:
    items = store.search(namespace)
    out: list[tuple[str, dict[str, Any]]] = []
    for item in items:
        out.append((item.key, item.value))  # type: ignore[arg-type]
    return out
