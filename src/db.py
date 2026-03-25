"""SQLite run history and document tracking.

Tables:
  - runs: each report generation run
  - documents: fetched source documents (for dedup)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from src.config.settings import DATA_DIR, DB_PATH

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id       TEXT PRIMARY KEY,
            topic        TEXT NOT NULL,
            normalized   TEXT DEFAULT '',
            status       TEXT DEFAULT 'running',
            sections     INTEGER DEFAULT 0,
            charts       INTEGER DEFAULT 0,
            report_chars INTEGER DEFAULT 0,
            qc_status    TEXT DEFAULT '',
            started_at   TEXT NOT NULL,
            finished_at  TEXT DEFAULT '',
            elapsed_sec  REAL DEFAULT 0,
            error        TEXT DEFAULT '',
            meta_json    TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS documents (
            doc_id      TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            title       TEXT DEFAULT '',
            url         TEXT DEFAULT '',
            published_at TEXT DEFAULT '',
            fetched_at  TEXT DEFAULT '',
            content_len INTEGER DEFAULT 0,
            run_id      TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_docs_url ON documents(url);
        CREATE INDEX IF NOT EXISTS idx_runs_topic ON runs(topic);
    """)
    conn.commit()
    conn.close()
    _ensure_cancel_requested_column()
    logger.info("Database initialised: %s", DB_PATH)


def _ensure_cancel_requested_column() -> None:
    """Idempotent migration: persist cancel requests for multi-worker / memory loss."""
    conn = _get_conn()
    info = conn.execute("PRAGMA table_info(runs)").fetchall()
    names = {row[1] for row in info}
    if "cancel_requested" not in names:
        conn.execute("ALTER TABLE runs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        logger.info("runs.cancel_requested column added")
    conn.close()


# ── Runs ─────────────────────────────────────────────────────


def insert_run(run_id: str, topic: str) -> None:
    """Insert or replace run row. Preserves ``cancel_requested`` so a user stop before
    ``run_report`` touches the DB is not wiped by ``REPLACE`` (same run_id as submit_run).
    """
    conn = _get_conn()
    prev = conn.execute("SELECT cancel_requested FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    keep_cancel = 1 if (prev and prev[0]) else 0
    conn.execute(
        """
        INSERT OR REPLACE INTO runs (run_id, topic, started_at, cancel_requested)
        VALUES (?, ?, ?, ?)
        """,
        (run_id, topic, datetime.now().isoformat(), keep_cancel),
    )
    conn.commit()
    conn.close()


def update_run(
    run_id: str,
    *,
    normalized: str = "",
    status: str = "",
    sections: int = 0,
    charts: int = 0,
    report_chars: int = 0,
    qc_status: str = "",
    elapsed_sec: float = 0,
    error: str = "",
    token_usage: dict | None = None,
) -> None:
    meta_json = json.dumps({"token_usage": token_usage}, ensure_ascii=False) if token_usage else ""
    conn = _get_conn()
    conn.execute(
        """
        UPDATE runs SET
            normalized = COALESCE(NULLIF(?, ''), normalized),
            status = COALESCE(NULLIF(?, ''), status),
            sections = CASE WHEN ? > 0 THEN ? ELSE sections END,
            charts = CASE WHEN ? > 0 THEN ? ELSE charts END,
            report_chars = CASE WHEN ? > 0 THEN ? ELSE report_chars END,
            qc_status = COALESCE(NULLIF(?, ''), qc_status),
            finished_at = ?,
            elapsed_sec = CASE WHEN ? > 0 THEN ? ELSE elapsed_sec END,
            error = COALESCE(NULLIF(?, ''), error),
            meta_json = COALESCE(NULLIF(?, ''), meta_json)
        WHERE run_id = ?
    """,
        (
            normalized,
            status,
            sections,
            sections,
            charts,
            charts,
            report_chars,
            report_chars,
            qc_status,
            datetime.now().isoformat(),
            elapsed_sec,
            elapsed_sec,
            error,
            meta_json,
            run_id,
        ),
    )
    conn.commit()
    conn.close()


def get_run(run_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def abandon_stale_running_runs() -> int:
    """Mark every ``running`` row as failed (no worker survives process restart).

    Call once at API startup so DB matches reality after uvicorn reload / crash.
    """
    msg = "服务已重启，任务未在执行，已标记为中断"
    conn = _get_conn()
    cur = conn.execute(
        """
        UPDATE runs SET
            status = 'failed',
            error = ?,
            finished_at = ?,
            cancel_requested = 0
        WHERE status = 'running'
        """,
        (msg, datetime.now().isoformat()),
    )
    conn.commit()
    n = cur.rowcount
    conn.close()
    if n:
        logger.info("Startup: marked %s orphaned running runs as failed", n)
    return n


def set_cancel_requested(run_id: str) -> bool:
    """Persist stop signal. Returns True if a *running* row was updated.

    Survives multi-worker uvicorn and in-memory ``Event`` loss after ``end_run``.
    """
    conn = _get_conn()
    cur = conn.execute(
        "UPDATE runs SET cancel_requested = 1 WHERE run_id = ? AND status = 'running'",
        (run_id,),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def list_runs(limit: int = 20) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_run(run_id: str) -> bool:
    """Delete a run row and its associated on-disk artifacts. Returns True if found."""
    conn = _get_conn()
    row = conn.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
    conn.commit()
    conn.close()

    # Clean up disk artifacts
    import shutil
    from src.config.settings import CHARTS_DIR, EVIDENCE_DIR, REPORTS_DIR

    for d in [CHARTS_DIR / run_id, EVIDENCE_DIR / f"chroma_{run_id}"]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    for ext in (".md", ".pdf"):
        p = REPORTS_DIR / f"report_{run_id}{ext}"
        if p.exists():
            p.unlink(missing_ok=True)
    events_dir = DATA_DIR / "runs" / run_id
    if events_dir.exists():
        shutil.rmtree(events_dir, ignore_errors=True)

    logger.info("Deleted run %s and its artifacts", run_id)
    return True


# ── Documents ────────────────────────────────────────────────


def insert_document(
    doc_id: str, source_name: str, title: str, url: str, published_at: str, content_len: int, run_id: str = ""
) -> None:
    conn = _get_conn()
    conn.execute(
        """
        INSERT OR IGNORE INTO documents
        (doc_id, source_name, title, url, published_at, fetched_at, content_len, run_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (doc_id, source_name, title, url, published_at, datetime.now().isoformat(), content_len, run_id),
    )
    conn.commit()
    conn.close()


def is_document_fetched(url: str) -> bool:
    """Check if a document with this URL has already been fetched."""
    conn = _get_conn()
    row = conn.execute("SELECT 1 FROM documents WHERE url = ? LIMIT 1", (url,)).fetchone()
    conn.close()
    return row is not None
