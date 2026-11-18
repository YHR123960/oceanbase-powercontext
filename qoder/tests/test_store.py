"""Domain rules of the workbench, exercised against the in-memory PowerContext stand-in."""

from __future__ import annotations

import pytest

from fake_powercontext import FakePCError
from yanxi.pc import SAFE_TEXT_BYTES
from yanxi.store import (
    BODY_LIMIT_BYTES,
    KIND_NOTE,
    KIND_PROGRESS,
    KIND_TASK,
    Workbench,
    WorkbenchError,
)


def test_scope_is_created_once_and_reused(wb: Workbench, fake) -> None:
    first = wb.ensure_scope()
    second = wb.ensure_scope()
    assert first == second
    assert len(fake.scopes) == 1
    assert list(fake.scopes)[0] == "qoder-yanxi-workbench:unit"


def test_note_roundtrip_is_powercontext_only(wb: Workbench, fake) -> None:
    created = wb.create_note(title="康有为的孔教运动", body="《不忍》杂志与孔教会的关系。",
                            course="近代史", tags=["思想史"], keywords=["孔教"])
    assert created["chunks"] == 1
    payloads = fake.payloads_for(KIND_NOTE)
    assert len(payloads) == 1
    assert payloads[0]["title"] == "康有为的孔教运动"
    # nothing else is stored: the app keeps no side database
    assert fake.payloads_for(KIND_TASK) == []
    assert fake.payloads_for(KIND_PROGRESS) == []


def test_labels_live_in_powercontext_not_the_app(wb: Workbench, fake) -> None:
    created = wb.create_note(title="B+树与LSM树对比", body="写放大", course="数据库",
                            tags=["索引"], keywords=["存储引擎"])
    artifact_id = created["atomic_memory_ids"][0]
    stored = fake.tags[artifact_id]
    assert "course:数据库" in stored
    assert "tag:索引" in stored
    assert "kw:存储引擎" in stored
    # public notes carry the bare label, the composite form is the PowerContext key
    note = next(item for item in wb.load()["notes"] if item["id"] == created["id"])
    assert "索引" in note["tags"]
    assert "存储引擎" in note["keywords"]


def test_long_note_is_chunked_under_the_server_byte_limit_and_rejoined(wb: Workbench, fake) -> None:
    body = "复" * 9000  # 27000 UTF-8 bytes, far past the 8192-byte remember limit
    created = wb.create_note(title="长文摘要", body=body, course="阅读")
    assert created["chunks"] > 1
    for record in fake.records_for(KIND_NOTE):
        assert len(record["text"].encode("utf-8")) <= SAFE_TEXT_BYTES, "each serialised record must fit"
    note = wb.load()["notes"][0]
    assert note["body"] == body
    assert note["chunks"] == created["chunks"]


def test_oversized_body_is_rejected_before_write(wb: Workbench, fake) -> None:
    with pytest.raises(WorkbenchError) as exc:
        wb.create_note(title="太大", body="x" * (BODY_LIMIT_BYTES + 10))
    assert exc.value.code == "body_too_large"
    assert fake.payloads_for(KIND_NOTE) == []


def test_blank_title_is_rejected(wb: Workbench) -> None:
    with pytest.raises(WorkbenchError) as exc:
        wb.create_note(title="   ")
    assert exc.value.code == "title_required"


def test_update_appends_a_revision_and_keeps_history(wb: Workbench, fake) -> None:
    created = wb.create_note(title="初稿", body="第一段", course="写作")
    note_id = created["id"]
    wb.update_note(note_id, body="第一段与第二段", title="改稿")
    payloads = fake.payloads_for(KIND_NOTE)
    assert len(payloads) == 2, "an update must append, never overwrite, Atomic Memory"
    assert sorted(item["seq"] for item in payloads) == [1, 2]
    note = wb.load()["notes"][0]
    assert note["title"] == "改稿"
    assert note["body"] == "第一段与第二段"
    assert note["seq"] == 2
    assert note["revisions"] == 2
    assert len(note["atomic_memory_ids"]) == 2


def test_status_change_records_progress_and_unchanged_status_does_not(wb: Workbench, fake) -> None:
    created = wb.create_note(title="复习计划", body="第 3 章", course="线性代数")
    note_id = created["id"]
    wb.set_note_status(note_id, "reading", memo="看完 3.1")
    assert len(fake.payloads_for(KIND_PROGRESS)) == 1
    wb.set_note_status(note_id, "reading", memo="重复设置")
    assert len(fake.payloads_for(KIND_PROGRESS)) == 1, "no event when nothing changed"
    wb.set_note_status(note_id, "mastered")
    events = wb.load()["progress"]
    assert [event["status"] for event in events] == ["reading", "mastered"]
    assert events[0]["memo"] == "看完 3.1"


def test_same_second_updates_order_by_note_revision(wb: Workbench, fake, monkeypatch) -> None:
    """Three status changes inside one second must still read as the order they happened.

    The Server makes no ordering promise and every progress event carries seq=1, so the
    note revision recorded on the event is what keeps the timeline consistent with the
    current status.
    """
    monkeypatch.setattr("yanxi.store.now", lambda: "2026-11-18T10:21:33.000042+08:00")
    note_id = wb.create_note(title="组会汇报骨架", body="四段式模板", course="科研写作")["id"]
    for status, memo in (("reading", "先把四段式写下来"),
                         ("mastered", "组会前又过了一遍"),
                         ("reading", "把局限页拆成两页")):
        wb.set_note_status(note_id, status, memo)

    def timeline() -> list[tuple[str, int]]:
        events = [item for item in wb.load()["progress"] if item["note_id"] == note_id]
        return [(item["status"], item["note_seq"]) for item in events]

    assert timeline() == [("reading", 2), ("mastered", 3), ("reading", 4)]
    state = wb.load()
    assert state["progress"][-1]["status"] == state["notes"][0]["status"], "timeline ends on the current status"

    fake.memories.reverse()
    assert timeline() == [("reading", 2), ("mastered", 3), ("reading", 4)], "order survives a reversed page"


def test_record_counts_separate_memories_from_visible_items(wb: Workbench) -> None:
    """Revisions pile up in PowerContext while the workspace still shows one item per entity."""
    note_id = wb.create_note(title="索引选择率", body="直方图", course="数据库")["id"]
    wb.update_note(note_id, body="直方图与选择率估算")
    counts = wb.load()["record_counts"]
    assert counts["notes"] == 1
    assert counts["note_records"] == 2


def test_unknown_status_is_rejected(wb: Workbench) -> None:
    created = wb.create_note(title="状态检查", body="")
    with pytest.raises(WorkbenchError):
        wb.set_note_status(created["id"], "done")


def test_bad_note_id_returns_404_not_empty_success(wb: Workbench) -> None:
    with pytest.raises(WorkbenchError) as exc:
        wb.update_note("note_does_not_exist", title="x")
    assert exc.value.status == 404
    with pytest.raises(WorkbenchError) as exc:
        wb.set_note_status("note_does_not_exist", "reading")
    assert exc.value.status == 404


def test_tasks_attach_to_notes_and_count_open_items(wb: Workbench, fake) -> None:
    note_id = wb.create_note(title="论文 A", body="方法部分", course="阅读")["id"]
    task_id = wb.create_task(note_id, "复现表 2")["id"]
    wb.create_task(note_id, "写Related Work")
    snapshot = wb.load()
    note = next(item for item in snapshot["notes"] if item["id"] == note_id)
    assert note["open_tasks"] == 2
    assert len(note["tasks"]) == 2
    wb.set_task_done(task_id, True)
    snapshot = wb.load()
    note = next(item for item in snapshot["notes"] if item["id"] == note_id)
    assert note["open_tasks"] == 1
    done = next(item for item in snapshot["tasks"] if item["id"] == task_id)
    assert done["done"] is True and done["completed_at"]


def test_retiring_hides_without_destroying_the_memory(wb: Workbench, fake) -> None:
    note_id = wb.create_note(title="临时想法", body="x")["id"]
    wb.retire_note(note_id)
    assert wb.load()["notes"] == []
    assert len(fake.payloads_for(KIND_NOTE)) == 2, "the retired note is still auditable in PowerContext"


def test_search_reports_powercontext_as_the_source(wb: Workbench, fake) -> None:
    a = wb.create_note(title="倒排索引原理", body="term dictionary postings", course="数据库")["id"]
    wb.create_note(title="无关内容", body="完全无关", course="体育")["id"]
    result = wb.search("倒排")
    ids = [item["id"] for item in result["notes"]]
    assert a in ids
    hit = next(item for item in result["notes"] if item["id"] == a)
    assert "text" in hit["matched_via"], "the Server's text search produced this hit"
    assert result["powercontext"]["search_hits"] >= 1
    assert result["powercontext"]["search_error"] is None


def test_tag_filtering_uses_the_server_side_label_index(wb: Workbench) -> None:
    keep = wb.create_note(title="带标签的笔记", body="x", course="数据库", tags=["索引"])["id"]
    other = wb.create_note(title="另一个标签", body="y", course="数据库", tags=["事务"])["id"]
    by_tag = wb.search("", tags=["tag:索引"])
    assert [item["id"] for item in by_tag["notes"]] == [keep]
    assert by_tag["notes"][0]["matched_via"] == ["tag"]
    both = wb.search("", tags=["tag:索引", "tag:事务"], tag_match="any")
    assert sorted(item["id"] for item in both["notes"]) == sorted([keep, other])
    none = wb.search("", tags=["tag:不存在"])
    assert none["notes"] == []


def test_empty_search_lists_everything(wb: Workbench) -> None:
    wb.create_note(title="甲", body="")
    wb.create_note(title="乙", body="")
    result = wb.search("")
    assert len(result["notes"]) == 2
    assert all(item["matched_via"] == ["scope-list"] for item in result["notes"])


def test_powercontext_outage_surfaces_as_an_error(wb: Workbench, fake) -> None:
    wb.create_note(title="正常", body="")
    fake.fail_next_write = True
    with pytest.raises(FakePCError):
        wb.create_note(title="写入失败", body="")
    assert [item["title"] for item in wb.load()["notes"]] == ["正常"]


def test_reload_returns_the_same_state_from_a_second_client(fake) -> None:
    """Two independent clients over one Server: proves state lives in PowerContext."""
    first = Workbench(fake, workspace="shared")
    note_id = first.create_note(title="跨进程复用", body="重启后仍应可见", course="验证")["id"]
    second = Workbench(fake, workspace="shared")
    notes = second.load()["notes"]
    assert [item["id"] for item in notes] == [note_id]
    assert notes[0]["body"] == "重启后仍应可见"
    assert first.scope_id == second.scope_id
