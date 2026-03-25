"""FastAPI service layer for the report generation system.

Endpoints:
  POST /api/report/run              — submit a new report generation task
  GET|POST|OPTIONS /api/report/{run_id}/cancel — cooperative stop (OPTIONS → 204)
  GET  /api/report/{run_id}         — check task status
  GET  /api/report/{run_id}/stream  — SSE: pipeline events (Sprint 7b)
  GET  /api/report/{run_id}/markdown — download Markdown
  GET  /api/report/{run_id}/pdf     — download PDF
  GET  /api/report/{run_id}/artifacts — list chart assets
  GET  /api/report/{run_id}/charts/{filename} — safe PNG download (Sprint 7b)
  GET  /api/runs                    — list historical runs
  GET  /api/health                  — liveness (Sprint 7b)
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.requests import Request
from pydantic import BaseModel
from starlette.staticfiles import StaticFiles

from src.config.settings import CHARTS_DIR, CORS_ORIGINS, REPORTS_DIR
from src.db import abandon_stale_running_runs, delete_run, get_run, init_db, insert_run, list_runs, update_run
from src.graph.run_control import begin_run, end_run, request_cancel
from src.telemetry.run_events import RunEventBus

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = _PROJECT_ROOT / "frontend" / "dist"


@asynccontextmanager
async def _lifespan(_: FastAPI):
    init_db()
    abandon_stale_running_runs()
    yield


app = FastAPI(title="行业研报 Agent API", version="2.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ACTIVE_TASKS: dict[str, threading.Thread] = {}


def _worker_alive(run_id: str) -> bool:
    """True only if this process started the background thread and it is still running."""
    t = _ACTIVE_TASKS.get(run_id)
    return t is not None and t.is_alive()


class RunRequest(BaseModel):
    topic: str
    max_reports: int = 8


class RunResponse(BaseModel):
    run_id: str
    topic: str
    status: str


def _safe_chart_path(run_id: str, filename: str) -> Path:
    """Resolve chart file under ``data/charts/{run_id}/``; reject traversal."""
    if not run_id or not filename:
        raise HTTPException(400, detail="Invalid path")
    if ".." in run_id or "/" in run_id or "\\" in run_id:
        raise HTTPException(400, detail="Invalid run_id")
    if any(sep in filename for sep in ("/", "\\")) or ".." in filename:
        raise HTTPException(400, detail="Invalid filename")
    name = Path(filename).name
    if name != filename:
        raise HTTPException(400, detail="Invalid filename")
    charts_root = CHARTS_DIR.resolve()
    base = (charts_root / run_id).resolve()
    try:
        base.relative_to(charts_root)
    except ValueError as e:
        raise HTTPException(400, detail="Invalid run_id") from e
    target = (base / name).resolve()
    try:
        target.relative_to(base)
    except ValueError as e:
        raise HTTPException(400, detail="Invalid path") from e
    return target


def _pipeline_terminal(ev: dict) -> bool:
    return ev.get("node") == "pipeline" and ev.get("phase") in ("end", "error", "cancelled")


async def _sse_event_generator(run_id: str):
    """Replay buffer or ``events.jsonl``, then live queue until pipeline ends or run finishes."""
    q, snapshot = RunEventBus.register_subscriber(run_id)
    try:
        for ev in snapshot:
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            if _pipeline_terminal(ev):
                return
        while True:
            try:
                ev = await asyncio.to_thread(q.get, timeout=20.0)
            except queue.Empty:
                row = get_run(run_id)
                st = row.get("status") if row else None
                if st in ("completed", "failed", "cancelled"):
                    break
                continue
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            if _pipeline_terminal(ev):
                break
    finally:
        RunEventBus.unregister_subscriber(run_id, q)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/report/run", response_model=RunResponse)
def submit_run(req: RunRequest):
    """Submit a new report generation task (runs in background thread)."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Persist run row *before* returning, so the client can open SSE immediately
    # (`GET .../stream` checks ``get_run``). ``run_report`` will INSERT OR REPLACE again.
    insert_run(run_id, req.topic)
    begin_run(run_id)

    def _worker():
        try:
            from src.graph.workflow import run_report

            run_report(req.topic, run_id=run_id)
        except Exception:
            logger.exception("Background report generation failed: %s", run_id)
        finally:
            _ACTIVE_TASKS.pop(run_id, None)

    t = threading.Thread(target=_worker, daemon=True, name=f"report-{run_id}")
    t.start()
    _ACTIVE_TASKS[run_id] = t

    return RunResponse(run_id=run_id, topic=req.topic, status="running")


@app.api_route("/api/report/{run_id}/cancel", methods=["GET", "POST", "OPTIONS"])
def cancel_report_run(run_id: str, request: Request):
    """Request cooperative cancellation (takes effect after the current graph step).

    GET is supported for compatibility: some proxies or cached clients issue GET and
    would otherwise receive 405 from a POST-only route.

    OPTIONS: bare ``OPTIONS`` (without CORS preflight headers) must not 405 — tools and
    some gateways probe with OPTIONS before POST.
    """
    if request.method == "OPTIONS":
        return Response(status_code=204)
    row = get_run(run_id)
    if not row:
        raise HTTPException(404, detail=f"Run {run_id} not found")
    if row.get("status") != "running":
        raise HTTPException(400, detail="任务未在运行中，无法停止")
    # DB says running but no thread (e.g. stale row after restart) — reconcile and succeed.
    if not _worker_alive(run_id):
        end_run(run_id)
        update_run(
            run_id,
            status="cancelled",
            error="任务已停止（无活跃执行进程，常见于服务重启后仍显示运行中）",
        )
        logger.info("Cancel reconciled stale run_id=%s (no active worker)", run_id)
        return {"ok": True, "run_id": run_id, "stale": True}
    if not request_cancel(run_id):
        raise HTTPException(400, detail="无法发送停止信号（任务可能已结束）")
    return {"ok": True, "run_id": run_id, "stale": False}


@app.get("/api/report/{run_id}")
def get_report_status(run_id: str):
    """Get the status of a report generation run."""
    row = get_run(run_id)
    if not row:
        raise HTTPException(404, detail=f"Run {run_id} not found")
    return JSONResponse(row)


@app.get("/api/report/{run_id}/stream")
async def stream_report_events(run_id: str):
    """Server-Sent Events: one JSON object per message (``data:`` line)."""
    row = get_run(run_id)
    if not row:
        raise HTTPException(404, detail=f"Run {run_id} not found")

    return StreamingResponse(
        _sse_event_generator(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/report/{run_id}/markdown")
def download_markdown(run_id: str):
    """Download the generated Markdown report."""
    path = REPORTS_DIR / f"report_{run_id}.md"
    if not path.exists():
        raise HTTPException(404, detail="Markdown report not found (may still be generating)")
    return FileResponse(
        path,
        media_type="text/markdown; charset=utf-8",
        filename=f"report_{run_id}.md",
    )


@app.get("/api/report/{run_id}/pdf")
def download_pdf(run_id: str):
    """Download the generated PDF report."""
    path = REPORTS_DIR / f"report_{run_id}.pdf"
    if not path.exists():
        raise HTTPException(404, detail="PDF report not found (may still be generating)")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"report_{run_id}.pdf",
    )


@app.get("/api/report/{run_id}/artifacts")
def list_artifacts(run_id: str):
    """List chart assets for a run."""
    chart_dir = CHARTS_DIR / run_id
    if not chart_dir.exists():
        raise HTTPException(404, detail="No artifacts found for this run")

    files = sorted(chart_dir.glob("*.png"))
    return {
        "run_id": run_id,
        "chart_count": len(files),
        "charts": [{"filename": f.name, "size_kb": round(f.stat().st_size / 1024, 1)} for f in files],
    }


@app.get("/api/report/{run_id}/charts/{filename}")
def get_chart_file(run_id: str, filename: str):
    """Serve a chart PNG for this run (path-safe)."""
    path = _safe_chart_path(run_id, filename)
    if not path.exists():
        raise HTTPException(404, detail="Chart not found")
    return FileResponse(path, media_type="image/png")


@app.get("/api/runs")
def get_runs(limit: int = 20):
    """List recent runs."""
    return list_runs(limit=limit)


@app.delete("/api/runs/{run_id}")
def delete_run_endpoint(run_id: str):
    """Delete a run and its artifacts."""
    if not delete_run(run_id):
        raise HTTPException(404, detail=f"Run {run_id} not found")
    return {"ok": True}


if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")
