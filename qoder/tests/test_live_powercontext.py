"""Same expectations as the unit tests, but against the real PowerContext Server.

Run with the service up (bash scripts/start_pc.sh). These tests are what prove the
in-memory stand-in in tests/fake_powercontext.py has not drifted from the official build.
"""

from __future__ import annotations

import json
import time

import pytest

from yanxi.pc import MAX_TEXT_BYTES, PCClient
from yanxi.store import KIND_NOTE, KIND_TASK, Workbench

pytestmark = pytest.mark.live


@pytest.fixture
def live_workbench(live_url: str) -> Workbench:
    workspace = f"live-{time.strftime('%H%M%S')}-{int(time.time() * 1000) % 1000}"
    workbench = Workbench(PCClient(base_url=live_url), workspace=workspace)
    workbench.ensure_scope()
    return workbench


def test_real_scope_creation_is_idempotent(live_workbench: Workbench) -> None:
    first = live_workbench.ensure_scope()
    second = PCClient(base_url=live_workbench.client.base_url)
    again = Workbench(second, workspace=live_workbench.workspace).ensure_scope()
    assert first == again


def test_note_survives_a_second_client(live_workbench: Workbench) -> None:
    body = "幂等集合 + 邻接矩阵的对偶关系。" * 3
    created = live_workbench.create_note(title="图算法笔记", body=body, course="离散数学",
                                        tags=["图论"], keywords=["邻接矩阵"])
    other = Workbench(PCClient(base_url=live_workbench.client.base_url),
                      workspace=live_workbench.workspace)
    notes = [item for item in other.load()["notes"] if item["id"] == created["id"]]
    assert len(notes) == 1
    assert notes[0]["body"] == body
    assert notes[0]["atomic_memory_ids"] == created["atomic_memory_ids"]


def test_long_body_actually_splits_on_the_real_byte_limit(live_workbench: Workbench) -> None:
    body = "索引选择率估计" * 2000  # ~24000 UTF-8 bytes
    created = live_workbench.create_note(title="数据库长文", body=body, course="数据库")
    assert created["chunks"] >= 3
    stored = live_workbench.client.list_atomic(live_workbench.scope_id, kind=KIND_NOTE)
    mine = [item for item in stored if json.loads(item["text"])["entity_id"] == created["id"]]
    assert len(mine) == created["chunks"]
    for record in mine:
        assert len(record["text"].encode("utf-8")) <= MAX_TEXT_BYTES
    rejoined = [item for item in live_workbench.load()["notes"] if item["id"] == created["id"]][0]
    assert rejoined["body"] == body


def test_server_side_tag_filter_and_text_search_are_used(live_workbench: Workbench) -> None:
    wanted = live_workbench.create_note(title="倒排索引与 B+ 树", body="postings list 压缩",
                                       course="数据库", tags=["存储"])["id"]
    live_workbench.create_note(title="完全不相关", body="跑步训练", course="体育", tags=["生活"])

    by_tag = live_workbench.search("", tags=["tag:存储"])
    assert [item["id"] for item in by_tag["notes"]] == [wanted]
    assert by_tag["powercontext"]["tag_filter_records"] >= 1

    by_text = live_workbench.search("postings")
    assert wanted in [item["id"] for item in by_text["notes"]]
    hit = next(item for item in by_text["notes"] if item["id"] == wanted)
    assert "text" in hit["matched_via"], "the Server, not the app, performed this match"
    assert by_text["powercontext"]["search_error"] is None


def test_labels_are_readable_back_from_the_server(live_workbench: Workbench) -> None:
    created = live_workbench.create_note(title="带标签", body="x", course="验证", tags=["甲"])
    artifact = created["atomic_memory_ids"][0]
    tags, etag = live_workbench.client.get_tags(live_workbench.scope_id, "atomic-memory", artifact)
    assert "course:验证" in tags and "tag:甲" in tags
    assert etag, "the Server must expose a validator for optimistic tag updates"


def test_progress_timeline_and_task_flow_on_real_memory(live_workbench: Workbench) -> None:
    note_id = live_workbench.create_note(title="复习计划", body="三轮")["id"]
    task_id = live_workbench.create_task(note_id, "整理卡片")["id"]
    live_workbench.set_note_status(note_id, "reading", memo="第一轮")
    live_workbench.set_task_done(task_id, True)

    snapshot = live_workbench.load()
    note = next(item for item in snapshot["notes"] if item["id"] == note_id)
    assert note["status"] == "reading" and note["open_tasks"] == 0
    event = next(item for item in snapshot["progress"] if item["note_id"] == note_id)
    assert event["status"] == "reading" and event["atomic_memory_id"].startswith("art_")

    task_records = live_workbench.client.list_atomic(live_workbench.scope_id, kind=KIND_TASK)
    entity = [json.loads(item["text"]) for item in task_records
              if json.loads(item["text"])["entity_id"] == task_id]
    assert sorted(item["seq"] for item in entity) == [1, 2], "the Server kept both revisions"


def test_same_second_status_changes_order_by_revision_on_the_server(live_workbench: Workbench,
                                                                   monkeypatch) -> None:
    """Real Atomic Memory records that all carry one identical timestamp.

    With ``at`` equal, only the note revision stored on each progress event can put the
    timeline back in the order the status changes actually happened.
    """
    monkeypatch.setattr("yanxi.store.now", lambda: "2026-11-18T10:21:33.000042+08:00")
    note_id = live_workbench.create_note(title="连点三次状态", body="同一秒内写入")["id"]
    for status in ("reading", "mastered", "reading"):
        live_workbench.set_note_status(note_id, status, memo=f"切到 {status}")

    snapshot = live_workbench.load()
    events = [item for item in snapshot["progress"] if item["note_id"] == note_id]
    assert {item["at"] for item in events} == {"2026-11-18T10:21:33.000042+08:00"}
    assert [(item["status"], item["note_seq"]) for item in events] == [
        ("reading", 2), ("mastered", 3), ("reading", 4)]
    note = next(item for item in snapshot["notes"] if item["id"] == note_id)
    assert events[-1]["status"] == note["status"], "the last timeline entry is the current status"


def test_delete_keeps_the_memory_auditable(live_workbench: Workbench) -> None:
    note_id = live_workbench.create_note(title="待删除", body="x")["id"]
    live_workbench.retire_note(note_id)
    assert [item for item in live_workbench.load()["notes"] if item["id"] == note_id] == []
    stored = [json.loads(item["text"]) for item in
              live_workbench.client.list_atomic(live_workbench.scope_id, kind=KIND_NOTE)]
    versions = sorted(item["seq"] for item in stored if item["entity_id"] == note_id)
    assert versions == [1, 2], "the create and the retire records both remain in PowerContext"
    tombstone = [item for item in stored if item["entity_id"] == note_id and item["op"] == "retire"]
    assert len(tombstone) == 1


def test_diagnostics_report_the_real_deployment(live_workbench: Workbench) -> None:
    live_workbench.load()
    data = live_workbench.diagnostics()
    assert data["reachable"] is True
    assert data["product"] == "powercontext"
    assert data["package_version"] == "0.1.dev1+g437aa0632.d20261118"
    assert "memory.explicit" in data["feature_contracts"]
    assert data["recent_calls"], "the UI provenance panel needs the observed HTTP calls"
    assert all(call["status"] and call["status"] < 400 for call in data["recent_calls"])
