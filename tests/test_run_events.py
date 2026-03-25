"""Sprint 7a: RunEventBus ordering, serialization, and concurrency."""

from __future__ import annotations

import concurrent.futures
import json

import pytest

from src.telemetry.run_events import (
    RunEventBus,
    emit_node_start,
    emit_pipeline_end,
    emit_pipeline_start,
    get_events_for_run,
    reset_telemetry,
)


@pytest.fixture(autouse=True)
def _telemetry_isolation() -> None:
    reset_telemetry()
    prev = RunEventBus.persist_jsonl
    RunEventBus.persist_jsonl = False
    yield
    RunEventBus.persist_jsonl = prev
    reset_telemetry()


def test_seq_monotonic_and_json_serializable() -> None:
    rid = "test_run_seq"
    emit_pipeline_start(rid)
    emit_node_start(rid, "plan")
    emit_pipeline_end(rid, detail="ok")
    events = get_events_for_run(rid)
    assert len(events) == 3
    assert [e["seq"] for e in events] == [1, 2, 3]
    for ev in events:
        json.dumps(ev, ensure_ascii=False)


def test_reset_run_clears_buffer() -> None:
    rid = "test_run_reset"
    emit_node_start(rid, "plan")
    RunEventBus.reset_run(rid)
    assert get_events_for_run(rid) == []


def test_subscriber_receives_live_events() -> None:
    rid = "test_run_sub"
    q, snapshot = RunEventBus.register_subscriber(rid)
    assert snapshot == []
    emit_pipeline_start(rid)
    ev = q.get(timeout=2.0)
    assert ev.get("node") == "pipeline" and ev.get("phase") == "start"
    emit_pipeline_end(rid, detail="done")
    ev2 = q.get(timeout=2.0)
    assert ev2.get("phase") == "end"
    RunEventBus.unregister_subscriber(rid, q)


def test_concurrent_publish_buffer_order_matches_seq() -> None:
    rid = "test_run_concurrent"
    n_per_thread = 40
    n_threads = 8

    def publish_many() -> None:
        for _ in range(n_per_thread):
            emit_node_start(rid, "plan")

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_threads) as ex:
        futures = [ex.submit(publish_many) for _ in range(n_threads)]
        for f in futures:
            f.result()

    events = get_events_for_run(rid)
    total = n_threads * n_per_thread
    assert len(events) == total
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(1, total + 1))
