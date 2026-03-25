"""Cooperative cancel between LangGraph steps (not mid-LLM call)."""

from __future__ import annotations

import threading
from typing import Dict

from src.db import get_run, set_cancel_requested


class RunCancelled(Exception):
    """Raised when the user requests stop; checked between graph.stream steps."""

    def __init__(self, message: str = "用户已停止任务") -> None:
        self.message = message
        super().__init__(message)


_lock = threading.Lock()
_cancel_events: Dict[str, threading.Event] = {}


def begin_run(run_id: str) -> None:
    """Ensure a cancel event exists (API may call before ``run_report`` starts)."""
    with _lock:
        _cancel_events.setdefault(run_id, threading.Event())


def end_run(run_id: str) -> None:
    with _lock:
        _cancel_events.pop(run_id, None)


def request_cancel(run_id: str) -> bool:
    """Signal cancellation. Persists to DB + always set in-process Event (race-safe)."""
    set_cancel_requested(run_id)
    with _lock:
        ev = _cancel_events.setdefault(run_id, threading.Event())
        ev.set()
    return True


def is_cancelled(run_id: str) -> bool:
    """True if Event set, DB ``cancel_requested``, or row already reconciled as cancelled."""
    with _lock:
        ev = _cancel_events.get(run_id)
        if ev and ev.is_set():
            return True
    row = get_run(run_id)
    if not row:
        return False
    if row.get("cancel_requested"):
        return True
    st = row.get("status")
    if st == "cancelled":
        return True
    return False
