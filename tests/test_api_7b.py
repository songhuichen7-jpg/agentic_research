"""Sprint 7b: health, chart route safety, SSE 404."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.server import _safe_chart_path


@pytest.fixture
def charts_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Must patch ``CHARTS_DIR`` after ``src.api.server`` is loaded (import binds the name)."""
    import src.api.server as srv

    monkeypatch.setattr(srv, "CHARTS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def client(charts_dir: Path) -> TestClient:
    from src.api.server import app

    return TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_chart_serves_png(client: TestClient, charts_dir: Path) -> None:
    rid = "20260101_120000"
    d = charts_dir / rid
    d.mkdir(parents=True)
    (d / "fig.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00")
    r = client.get(f"/api/report/{rid}/charts/fig.png")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/png")


def test_safe_chart_path_rejects_traversal() -> None:
    with pytest.raises(HTTPException) as exc:
        _safe_chart_path("20260101_120000", "a/b.png")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        _safe_chart_path("20260101_120000", "..%2Fsecret.png")
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        _safe_chart_path("..%2Fother", "x.png")
    assert exc.value.status_code == 400


def test_stream_requires_existing_run(client: TestClient) -> None:
    r = client.get("/api/report/__no_such_run__/stream")
    assert r.status_code == 404


def test_cancel_accepts_post_and_get(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.api.server as srv

    monkeypatch.setattr(srv, "request_cancel", lambda rid: True)
    monkeypatch.setattr(srv, "_worker_alive", lambda rid: True)  # else stale-reconcile path runs
    monkeypatch.setattr(
        srv,
        "get_run",
        lambda rid: {"run_id": rid, "status": "running", "topic": "t"} if rid == "rid_cancel" else None,
    )
    r_post = client.post("/api/report/rid_cancel/cancel")
    assert r_post.status_code == 200
    assert r_post.json().get("ok") is True

    r_get = client.get("/api/report/rid_cancel/cancel")
    assert r_get.status_code == 200
    assert r_get.json().get("ok") is True

    r_opt = client.options("/api/report/rid_cancel/cancel")
    assert r_opt.status_code == 204
