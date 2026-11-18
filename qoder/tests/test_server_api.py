"""HTTP behaviour of the workbench: routing, status codes and honest failure reporting."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from fake_powercontext import FakePowerContext
from yanxi import server as server_module


@pytest.fixture
def app(monkeypatch):
    fake = FakePowerContext()
    monkeypatch.setattr(server_module, "PCClient", lambda base_url=None, **kw: fake)
    monkeypatch.setattr(server_module, "_config", {"workspace": "api", "pc_url": "http://fake"})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, fake
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def call(base: str, method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_health_reports_the_real_server(app) -> None:
    base, fake = app
    status, body = call(base, "GET", "/api/health")
    assert status == 200
    assert body["data"]["powercontext"]["product"] == "powercontext"
    assert body["data"]["scope_id"].startswith("scp_fake_")


def test_create_read_update_delete_flow(app) -> None:
    base, fake = app
    status, body = call(base, "POST", "/api/notes",
                        {"title": "会议纪要", "body": "三条行动项", "course": "工作",
                         "tags": "待办,周会", "keywords": "行动项"})
    assert status == 200 and body["ok"] is True
    note_id = body["data"]["id"]

    status, body = call(base, "GET", "/api/state")
    assert status == 200
    note = next(item for item in body["data"]["notes"] if item["id"] == note_id)
    assert note["tags"] == ["待办", "周会"]
    assert note["status_label"] == "未开始"

    status, body = call(base, "PATCH", f"/api/notes/{note_id}", {"status": "reading", "memo": "先看结论"})
    assert status == 200 and body["data"]["seq"] == 2

    status, body = call(base, "POST", "/api/tasks", {"note_id": note_id, "title": "整理行动项"})
    task_id = body["data"]["id"]
    status, body = call(base, "POST", f"/api/tasks/{task_id}/done", {"done": True})
    assert body["data"]["done"] is True

    status, body = call(base, "GET", "/api/state")
    note = next(item for item in body["data"]["notes"] if item["id"] == note_id)
    assert note["status"] == "reading" and note["open_tasks"] == 0
    assert body["data"]["progress"][0]["status"] == "reading"

    status, body = call(base, "DELETE", f"/api/notes/{note_id}")
    assert status == 200
    status, body = call(base, "GET", "/api/state")
    assert [item["id"] for item in body["data"]["notes"]] == []
    # deletion is a tombstone: the memories remain in PowerContext and stay auditable
    assert len(fake.payloads_for("yanxi.note.v1")) >= 3


def test_validation_errors_are_400_with_codes(app) -> None:
    base, _ = app
    status, body = call(base, "POST", "/api/notes", {"title": "   "})
    assert status == 400 and body["ok"] is False
    assert body["error"]["code"] == "title_required"
    status, body = call(base, "POST", f"/api/notes/missing/status", {"status": "nonsense"})
    assert status in (400, 404)


def test_malformed_json_is_rejected(app) -> None:
    base, _ = app
    request = urllib.request.Request(base + "/api/notes", data=b"{not json",
                                     method="POST", headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(request, timeout=10)
    assert excinfo.value.code == 400


def test_powercontext_failure_is_502_never_a_fake_success(app) -> None:
    base, fake = app
    fake.fail_next_write = True
    status, body = call(base, "POST", "/api/notes", {"title": "会失败", "body": ""})
    assert status == 502
    assert body["ok"] is False
    assert body["error"]["code"] == "powercontext_error"
    assert "simulated PowerContext outage" in body["error"]["message"]
    assert "powercontext" in body
    status, body = call(base, "GET", "/api/state")
    assert body["data"]["notes"] == []


def test_search_endpoint_exposes_provenance(app) -> None:
    base, _ = app
    call(base, "POST", "/api/notes", {"title": "向量检索入门", "body": "HNSW 图索引", "course": "检索",
                                     "tags": "ANN"})
    call(base, "POST", "/api/notes", {"title": "无关", "body": "无关"})
    status, body = call(base, "GET", "/api/search?q=HNSW")
    assert status == 200
    assert [item["title"] for item in body["data"]["notes"]] == ["向量检索入门"]
    # PowerContext's text search and the app's substring pass both match here, and the
    # response says so instead of attributing everything to the Server.
    assert set(body["data"]["notes"][0]["matched_via"]) == {"text", "client-scan"}
    assert body["data"]["powercontext"]["search_hits"] >= 1
    status, body = call(base, "GET", "/api/search?q=&tags=tag%3AANN")
    assert [item["title"] for item in body["data"]["notes"]] == ["向量检索入门"]


def test_pc_diagnostics_endpoint(app) -> None:
    base, _fake = app
    status, body = call(base, "GET", "/api/pc")
    assert status == 200
    data = body["data"]
    assert data["product"] == "powercontext"
    assert data["kinds"] == ["yanxi.note.v1", "yanxi.task.v1", "yanxi.progress.v1"]
    assert data["workspace"] == "api"
    assert data["scope_id"].startswith("scp_fake_")


def test_unknown_route_and_static_traversal_are_blocked(app) -> None:
    base, _ = app
    status, _body = call(base, "GET", "/api/nope")
    assert status == 404
    for attempt in ("/static/../../../etc/passwd", "/static/%2e%2e/%2e%2e/pc.py", "/static/conftest.py"):
        request = urllib.request.Request(base + attempt, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                code = response.status
        except urllib.error.HTTPError as exc:
            code = exc.code
        assert code == 404, f"{attempt} must not be served"


def test_index_page_is_served(app) -> None:
    base, _ = app
    with urllib.request.urlopen(base + "/", timeout=10) as response:
        assert response.status == 200
        assert "text/html" in response.headers.get("Content-Type", "")
        body = response.read().decode("utf-8")
    assert "研习工作台" in body
