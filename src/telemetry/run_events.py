"""Run-level event bus for pipeline telemetry (Sprint 7a).

Thread-safe publish; optional JSONL append under ``data/runs/{run_id}/events.jsonl``.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from src.config.settings import DATA_DIR

logger = logging.getLogger(__name__)

Phase = Literal["start", "end", "error", "cancelled", "detail"]
Actor = Literal["system", "agent"]

# LangGraph node id → (actor, short Chinese title) — aligned with DEVELOPMENT_PLAN §7.3
NODE_META: dict[str, tuple[Actor, str]] = {
    "collect_documents": ("system", "采集研报与元数据"),
    "plan": ("agent", "生成研究大纲与章节"),
    "web_search": ("system", "博查搜索补证据"),
    "build_evidence": ("system", "证据分块与向量入库"),
    "write_sections": ("agent", "分章写作与引用"),
    "charts": ("agent", "图表规划与渲染"),
    "assemble": ("system", "组装 Markdown 报告"),
    "quality_check": ("system", "质量检查"),
    "export_pdf": ("system", "导出 PDF"),
    "pipeline": ("system", "流水线"),
}


RUNS_DIR = DATA_DIR / "runs"


def load_persisted_events(run_id: str) -> list[dict[str, Any]]:
    """Load ``events.jsonl`` for *run_id* (e.g. after API restart when buffer is empty)."""
    path = RUNS_DIR / run_id / "events.jsonl"
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Cannot read events.jsonl: %s", e)
        return []
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("Skipping invalid JSONL line in %s", path)
    return out


class RunEventBus:
    """In-memory event buffer per run_id + monotonic seq; optional JSONL persistence."""

    _lock = threading.Lock()
    _seq: dict[str, int] = {}
    _buffers: dict[str, list[dict[str, Any]]] = {}
    _subscribers: dict[str, list[queue.Queue]] = {}
    persist_jsonl: bool = True

    @classmethod
    def reset(cls) -> None:
        """Clear all in-memory state (tests)."""
        with cls._lock:
            cls._seq.clear()
            cls._buffers.clear()
            cls._subscribers.clear()

    @classmethod
    def reset_run(cls, run_id: str) -> None:
        with cls._lock:
            cls._seq.pop(run_id, None)
            cls._buffers.pop(run_id, None)
            # Preserve subscribers — SSE clients may already be connected
            # between the POST response and the worker thread starting.

    @classmethod
    def publish(
        cls,
        run_id: str,
        *,
        node: str,
        phase: Phase,
        actor: Actor,
        title: str,
        detail: str = "",
        error: str | None = None,
    ) -> dict[str, Any]:
        if not run_id:
            logger.debug("publish skipped: empty run_id")
            return {}

        with cls._lock:
            seq = cls._seq.get(run_id, 0) + 1
            cls._seq[run_id] = seq

            event: dict[str, Any] = {
                "seq": seq,
                "ts": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "node": node,
                "phase": phase,
                "actor": actor,
                "title": title,
            }
            if detail:
                event["detail"] = detail[:2000]
            if error is not None:
                event["error"] = error[:2000]

            cls._buffers.setdefault(run_id, []).append(event)

            if cls.persist_jsonl:
                cls._append_jsonl(run_id, event)

            for q in cls._subscribers.get(run_id, []):
                try:
                    q.put_nowait(dict(event))
                except Exception:
                    logger.debug("subscriber queue put failed", exc_info=True)

        logger.debug("run_event seq=%s node=%s phase=%s", seq, node, phase)
        return event

    @classmethod
    def _append_jsonl(cls, run_id: str, event: dict[str, Any]) -> None:
        try:
            d = RUNS_DIR / run_id
            d.mkdir(parents=True, exist_ok=True)
            path = d / "events.jsonl"
            line = json.dumps(event, ensure_ascii=False) + "\n"
            path.open("a", encoding="utf-8").write(line)
        except OSError as e:
            logger.warning("Failed to append events.jsonl: %s", e)

    @classmethod
    def get_buffer(cls, run_id: str) -> list[dict[str, Any]]:
        with cls._lock:
            return list(cls._buffers.get(run_id, []))

    @classmethod
    def register_subscriber(cls, run_id: str) -> tuple[queue.Queue, list[dict[str, Any]]]:
        """Register a queue that receives a copy of each new event; return replay snapshot (buffer or jsonl)."""
        q: queue.Queue = queue.Queue()
        with cls._lock:
            buf = cls._buffers.get(run_id, [])
            snapshot = [dict(e) for e in buf]
            cls._subscribers.setdefault(run_id, []).append(q)
        if not snapshot:
            snapshot = load_persisted_events(run_id)
        return q, snapshot

    @classmethod
    def unregister_subscriber(cls, run_id: str, q: queue.Queue) -> None:
        with cls._lock:
            subs = cls._subscribers.get(run_id)
            if not subs:
                return
            if q in subs:
                subs.remove(q)
            if not subs:
                cls._subscribers.pop(run_id, None)


def emit_node_start(run_id: str, node: str, detail: str = "") -> dict[str, Any]:
    actor, title = NODE_META.get(node, ("system", node))
    return RunEventBus.publish(
        run_id,
        node=node,
        phase="start",
        actor=actor,
        title=title,
        detail=detail,
    )


def emit_node_end(run_id: str, node: str, detail: str = "") -> dict[str, Any]:
    actor, title = NODE_META.get(node, ("system", node))
    return RunEventBus.publish(
        run_id,
        node=node,
        phase="end",
        actor=actor,
        title=title,
        detail=detail,
    )


def emit_node_error(run_id: str, node: str, message: str) -> dict[str, Any]:
    actor, title = NODE_META.get(node, ("system", node))
    return RunEventBus.publish(
        run_id,
        node=node,
        phase="error",
        actor=actor,
        title=title,
        error=message,
    )


def emit_node_detail(run_id: str, node: str, detail: str) -> dict[str, Any]:
    """Emit a granular progress event within a node (e.g. LLM tokens, fetch status)."""
    actor, title = NODE_META.get(node, ("system", node))
    return RunEventBus.publish(
        run_id,
        node=node,
        phase="detail",
        actor=actor,
        title=title,
        detail=detail,
    )


def emit_pipeline_start(run_id: str) -> dict[str, Any]:
    return RunEventBus.publish(
        run_id,
        node="pipeline",
        phase="start",
        actor="system",
        title="开始执行",
        detail="LangGraph 流水线启动",
    )


def emit_pipeline_end(run_id: str, detail: str = "") -> dict[str, Any]:
    return RunEventBus.publish(
        run_id,
        node="pipeline",
        phase="end",
        actor="system",
        title="全部完成",
        detail=detail or "流水线正常结束",
    )


def emit_pipeline_error(run_id: str, message: str) -> dict[str, Any]:
    return RunEventBus.publish(
        run_id,
        node="pipeline",
        phase="error",
        actor="system",
        title="执行失败",
        error=message,
    )


def emit_pipeline_cancelled(run_id: str, message: str = "用户已停止任务") -> dict[str, Any]:
    return RunEventBus.publish(
        run_id,
        node="pipeline",
        phase="cancelled",
        actor="system",
        title="已停止",
        detail=message[:500],
        error=message[:2000],
    )


def get_events_for_run(run_id: str) -> list[dict[str, Any]]:
    """Return a copy of in-memory events for *run_id* (tests / debugging)."""
    return RunEventBus.get_buffer(run_id)


def reset_telemetry() -> None:
    """Reset all telemetry state (e.g. before tests)."""
    RunEventBus.reset()
