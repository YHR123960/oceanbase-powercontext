"""Domain layer of 研习工作台: notes, tasks and progress kept as PowerContext Atomic Memory.

There is intentionally no local cache and no local database. Every read goes back to
PowerContext, so browser refresh, application restart and even a PowerContext process
restart all show the same data - the Server is the only place state lives.

Because the official contract forbids in-place edits (a revise request that carries a
`citation` is rejected as unsupported), mutations append a new Atomic Memory with an
incremented ``seq`` and reads fold the event log down to the current state. The history
that is discarded by folding is exactly what powers the progress timeline.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .pc import SAFE_TEXT_BYTES, PCClient, PCError, chunk_text, utf8_len

KIND_NOTE = "yanxi.note.v1"
KIND_TASK = "yanxi.task.v1"
KIND_PROGRESS = "yanxi.progress.v1"
KINDS = (KIND_NOTE, KIND_TASK, KIND_PROGRESS)

NOTE_STATUSES = ("unread", "reading", "mastered")
STATUS_LABELS = {"unread": "未开始", "reading": "在读", "mastered": "已掌握"}
TAG_MAX = 32
TAG_QUERY_MAX = 16
TAG_LEN = 64
BODY_LIMIT_BYTES = 200_000  # ~26 Atomic Memory records at the Server's 8192-byte ceiling


class WorkbenchError(Exception):
    def __init__(self, message: str, *, status: int = 400, code: str = "invalid"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


@dataclass
class Note:
    entity_id: str
    seq: int
    title: str
    body: str
    course: str = ""
    tags: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    status: str = "unread"
    created_at: str = ""
    updated_at: str = ""
    retired: bool = False
    record_ids: list[str] = field(default_factory=list)
    revisions: int = 1
    chunks: int = 1

    def to_public(self) -> dict:
        return {
            "id": self.entity_id,
            "seq": self.seq,
            "revisions": self.revisions,
            "title": self.title,
            "body": self.body,
            "course": self.course,
            "tags": self.tags,
            "keywords": self.keywords,
            "status": self.status,
            "status_label": STATUS_LABELS.get(self.status, self.status),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "atomic_memory_ids": self.record_ids,
            "chunks": self.chunks,
        }


@dataclass
class Task:
    entity_id: str
    seq: int
    note_id: str
    title: str
    done: bool = False
    created_at: str = ""
    updated_at: str = ""
    completed_at: str | None = None
    retired: bool = False
    record_ids: list[str] = field(default_factory=list)
    revisions: int = 1

    def to_public(self) -> dict:
        return {
            "id": self.entity_id,
            "seq": self.seq,
            "revisions": self.revisions,
            "note_id": self.note_id,
            "title": self.title,
            "done": self.done,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "atomic_memory_id": self.record_ids[-1] if self.record_ids else None,
        }


def now() -> str:
    """Microsecond-precision local timestamp: same-second updates must still order correctly."""
    return datetime.now().astimezone().isoformat(timespec="microseconds")


class Workbench:
    """All persistence for the workbench, implemented over PowerContext Atomic Memory."""

    def __init__(self, client: PCClient, workspace: str = "default"):
        self.client = client
        self.workspace = workspace
        self._scope_id: str | None = None

    # ------------------------------------------------------------------- scope

    @property
    def scope_id(self) -> str:
        if not self._scope_id:
            self._scope_id = self.ensure_scope()
        return self._scope_id

    def scope_key(self) -> str:
        return f"qoder-yanxi-workbench:{self.workspace}"

    def ensure_scope(self) -> str:
        """Create the workspace Scope once; PowerContext reuses it via idempotency_key."""
        descriptor = self.client.create_scope(
            title=f"研习工作台 · {self.workspace}",
            summary=("学习资料、阅读笔记与关联待办的工作上下文。所有条目以 Atomic Memory 形式保存在 "
                     "PowerContext，应用不落本地库。"),
            idempotency_key=self.scope_key(),
        )
        self._scope_id = descriptor["scope_id"]
        return self._scope_id

    # ------------------------------------------------------------- low level IO

    def _write(self, kind: str, payload: dict, *, description: str | None = None) -> list[dict]:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if utf8_len(text) > SAFE_TEXT_BYTES:
            raise WorkbenchError(
                f"内部错误：单条记录 {utf8_len(text)} 字节超过 {SAFE_TEXT_BYTES}", code="payload_too_large"
            )
        return self.client.remember(self.scope_id, kind, text, description=description)

    def _write_chunks(self, kind: str, base_payload: dict, body: str,
                      description: str | None) -> tuple[list[dict], int]:
        """Split the body so each *serialised* record fits the Server's byte limit.

        The envelope (metadata plus JSON escaping) costs bytes too, so the budget is
        measured against the real record rather than the raw body.
        """
        overhead = utf8_len(json.dumps({**base_payload, "body": "", "chunk_index": 0, "chunk_count": 1},
                                       ensure_ascii=False, separators=(",", ":")))
        budget = max(SAFE_TEXT_BYTES - overhead, 256)
        chunks = chunk_text(body, budget) if body else [""]
        written: list[dict] = []
        for index, chunk in enumerate(chunks):
            written.extend(self._write(
                kind,
                {**base_payload, "body": chunk, "chunk_index": index, "chunk_count": len(chunks)},
                description=description,
            ))
        return written, len(chunks)

    def _read_kind(self, kind: str) -> tuple[list[dict], list[dict]]:
        """Return (records, parse_errors); every record is one Atomic Memory."""
        records = self.client.list_atomic(self.scope_id, kind=kind, states=["active"])
        decoded: list[dict] = []
        errors: list[dict] = []
        for record in records:
            try:
                payload = json.loads(record["text"])
            except (ValueError, KeyError) as exc:
                errors.append({"artifact_id": (record.get("artifact") or {}).get("artifact_id"),
                               "error": str(exc)})
                continue
            payload["_record"] = record
            decoded.append(payload)
        return decoded, errors

    @staticmethod
    def _identity(payload: dict) -> str:
        return (payload.get("_record", {}).get("artifact") or {}).get("artifact_id", "")

    @staticmethod
    def _sort_key(payload: dict) -> tuple:
        return (str(payload.get("created_at", "")), int(payload.get("seq", 0)))

    def _fold_notes(self, payloads: list[dict]) -> dict[str, Note]:
        """Collapse the append-only log into current notes, stitching body chunks together."""
        by_entity: dict[str, dict[int, list[dict]]] = {}
        for payload in payloads:
            entity = payload.get("entity_id")
            if not entity:
                continue
            by_entity.setdefault(entity, {}).setdefault(int(payload.get("seq", 0)), []).append(payload)

        notes: dict[str, Note] = {}
        for entity, by_seq in by_entity.items():
            latest_seq = max(by_seq)
            # body may span several Atomic Memory records because of the Server's 8192-byte limit
            parts = sorted(by_seq[latest_seq], key=lambda p: int(p.get("chunk_index", 0)))
            merged = dict(parts[0])
            if len(parts) > 1:
                merged["body"] = "".join(str(p.get("body", "")) for p in parts)
            merged["_record"] = parts[-1]["_record"]
            merged["chunks"] = len(parts)
            merged["revisions"] = latest_seq
            if merged.get("op") == "retire":
                note = self._note_from_payload(entity, merged)
                note.retired = True
                notes[entity] = note
                continue
            # every Atomic Memory that ever contributed to this entity, oldest revision first
            record_ids: list[str] = []
            created_at = merged.get("created_at", "")
            for seq in sorted(by_seq):
                for part in sorted(by_seq[seq], key=lambda p: int(p.get("chunk_index", 0))):
                    identity = self._identity(part)
                    if identity:
                        record_ids.append(identity)
                first = by_seq[seq][0].get("created_at")
                if first and (not created_at or first < created_at):
                    created_at = first
            merged["created_at"] = created_at or merged.get("updated_at", "")
            merged["_all_record_ids"] = record_ids
            notes[entity] = self._note_from_payload(entity, merged)
        return notes

    @staticmethod
    def _note_from_payload(entity: str, payload: dict) -> Note:
        record = payload.get("_record", {})
        record_ids = payload.get("_all_record_ids") or [record.get("artifact", {}).get("artifact_id", "")]
        return Note(
            entity_id=entity,
            seq=int(payload.get("seq", 0)),
            title=str(payload.get("title", "")),
            body=str(payload.get("body", "")),
            course=str(payload.get("course", "")),
            tags=list(payload.get("tags", [])),
            keywords=list(payload.get("keywords", [])),
            status=payload.get("status") if payload.get("status") in NOTE_STATUSES else "unread",
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            record_ids=[item for item in record_ids if item],
            revisions=int(payload.get("revisions", 1)),
            chunks=int(payload.get("chunks", 1)),
        )

    def _fold_tasks(self, payloads: list[dict]) -> dict[str, Task]:
        by_entity: dict[str, list[dict]] = {}
        for payload in payloads:
            entity = payload.get("entity_id")
            if entity:
                by_entity.setdefault(entity, []).append(payload)
        tasks: dict[str, Task] = {}
        for entity, history in by_entity.items():
            history.sort(key=self._sort_key)
            latest = history[-1]
            tasks[entity] = Task(
                entity_id=entity,
                seq=int(latest.get("seq", 0)),
                note_id=str(latest.get("note_id", "")),
                title=str(latest.get("title", "")),
                done=bool(latest.get("done", False)),
                created_at=str(latest.get("created_at", "")),
                updated_at=str(latest.get("updated_at", "")),
                completed_at=latest.get("completed_at"),
                retired=latest.get("op") == "retire",
                record_ids=[self._identity(item) for item in history],
                revisions=len(history),
            )
        return tasks

    # ------------------------------------------------------------------ reading

    def load(self) -> dict:
        """Read the whole workspace back from PowerContext. No caching: callers get Server truth."""
        note_payloads, note_errors = self._read_kind(KIND_NOTE)
        task_payloads, task_errors = self._read_kind(KIND_TASK)
        progress_payloads, progress_errors = self._read_kind(KIND_PROGRESS)

        notes = self._fold_notes(note_payloads)
        tasks = self._fold_tasks(task_payloads)
        progress = sorted(
            (item for item in progress_payloads if item.get("op") != "retire"),
            # note_seq is the decisive tiebreaker: every status change appends revision n+1
            key=lambda item: (str(item.get("at", "")), int(item.get("note_seq") or 0), int(item.get("seq") or 0)),
        )

        live_notes = [note for note in notes.values() if not note.retired]
        live_tasks = [task for task in tasks.values() if not task.retired]
        live_notes.sort(key=lambda note: note.updated_at, reverse=True)
        live_tasks.sort(key=lambda task: (task.done, task.updated_at))
        tasks_by_note: dict[str, list[dict]] = {}
        for task in live_tasks:
            tasks_by_note.setdefault(task.note_id, []).append(task.to_public())
        public_notes: list[dict] = []
        for note in live_notes:
            payload = note.to_public()
            payload["open_tasks"] = sum(1 for item in tasks_by_note.get(note.entity_id, []) if not item["done"])
            payload["tasks"] = tasks_by_note.get(note.entity_id, [])
            public_notes.append(payload)

        return {
            "notes": public_notes,
            "tasks": [task.to_public() for task in live_tasks],
            "progress": [
                {
                    "id": item.get("entity_id"),
                    "note_id": item.get("note_id"),
                    "note_title": item.get("note_title", ""),
                    "status": item.get("status"),
                    "status_label": STATUS_LABELS.get(item.get("status"), item.get("status")),
                    "note_seq": int(item.get("note_seq") or 0),
                    "memo": item.get("memo", ""),
                    "at": item.get("at", ""),
                    "atomic_memory_id": self._identity(item),
                }
                for item in progress
            ][-50:],
            "parse_errors": note_errors + task_errors + progress_errors,
            "record_counts": {
                "note_records": len(note_payloads),
                "task_records": len(task_payloads),
                "progress_records": len(progress_payloads),
                "notes": len(live_notes),
                "tasks": len(live_tasks),
            },
        }

    # ------------------------------------------------------------------ writing

    def _clean_tags(self, tags: list[str], prefix: str = "tag") -> list[str]:
        out: list[str] = []
        for raw in tags:
            value = str(raw).strip()
            if not value:
                continue
            composite = f"{prefix}:{value}"[:TAG_LEN]
            if composite not in out:
                out.append(composite)
        return out[:TAG_MAX]

    def create_note(self, *, title: str, body: str = "", course: str = "",
                    tags: list[str] | None = None, keywords: list[str] | None = None) -> dict:
        title = str(title or "").strip()
        if not title:
            raise WorkbenchError("标题不能为空", code="title_required")
        if len(title) > 200:
            raise WorkbenchError("标题请控制在 200 字以内", code="title_too_long")
        body = str(body or "")
        if utf8_len(body) > BODY_LIMIT_BYTES:
            raise WorkbenchError(
                f"正文 {utf8_len(body)} 字节超过上限 {BODY_LIMIT_BYTES}", code="body_too_large"
            )
        status = "unread"
        stamp = now()
        entity_id = f"note_{uuid.uuid4().hex[:12]}"
        tag_list = self._clean_tags(tags or [])
        keyword_list = self._clean_tags(keywords or [], prefix="kw")
        label_tags = tag_list + keyword_list
        if course.strip():
            label_tags = self._clean_tags([course.strip()], prefix="course") + label_tags
        label_tags = self._dedup(label_tags)[:TAG_MAX]

        description = f"{title}｜{STATUS_LABELS[status]}"[:200]
        payload_base = {
            "entity_id": entity_id, "seq": 1, "op": "create", "title": title, "course": course.strip(),
            "tags": [t.split(":", 1)[1] for t in tag_list], "keywords": [t.split(":", 1)[1] for t in keyword_list],
            "status": status, "created_at": stamp, "updated_at": stamp,
        }
        written, chunks = self._write_chunks(KIND_NOTE, payload_base, body, description)
        artifact = (written[0].get("artifact") or {}) if written else {}
        if label_tags and artifact.get("artifact_id"):
            self.client.replace_tags(self.scope_id, artifact.get("family", "atomic-memory"),
                                     artifact["artifact_id"], label_tags)
        return {"id": entity_id, "atomic_memory_ids": [
            (item.get("artifact") or {}).get("artifact_id") for item in written], "chunks": chunks}

    def update_note(self, note_id: str, *, title: str | None = None, body: str | None = None,
                    course: str | None = None, tags: list[str] | None = None,
                    keywords: list[str] | None = None, status: str | None = None,
                    reason: str = "") -> dict:
        notes = self.load()["notes"]
        existing = next((note for note in notes if note["id"] == note_id), None)
        if existing is None:
            raise WorkbenchError("找不到这条笔记", status=404, code="note_not_found")
        current = existing
        stamp = now()
        next_seq = int(current["seq"]) + 1
        new_status = status if status in NOTE_STATUSES else current["status"]
        new_title = current["title"] if title is None else str(title).strip()
        if not new_title:
            raise WorkbenchError("标题不能为空", code="title_required")
        new_body = current["body"] if body is None else str(body)
        if utf8_len(new_body) > BODY_LIMIT_BYTES:
            raise WorkbenchError("正文超出长度上限", code="body_too_large")
        new_course = current["course"] if course is None else str(course).strip()
        tag_list = self._clean_tags(tags) if tags is not None else self._clean_tags(current["tags"])
        keyword_list = (self._clean_tags(keywords, prefix="kw") if keywords is not None
                        else self._clean_tags(current["keywords"], prefix="kw"))
        label_tags = tag_list + keyword_list
        if new_course:
            label_tags = self._clean_tags([new_course], prefix="course") + label_tags
        label_tags = self._dedup(label_tags)[:TAG_MAX]

        payload_base = {
            "entity_id": note_id, "seq": next_seq, "op": "update", "title": new_title, "course": new_course,
            "tags": [t.split(":", 1)[1] for t in tag_list], "keywords": [t.split(":", 1)[1] for t in keyword_list],
            "status": new_status, "created_at": current["created_at"], "updated_at": stamp,
        }
        written, chunks = self._write_chunks(
            KIND_NOTE, payload_base, new_body, f"{new_title}｜{STATUS_LABELS[new_status]}"[:200])
        artifact = (written[0].get("artifact") or {}) if written else {}
        if artifact.get("artifact_id"):
            self.client.replace_tags(self.scope_id, artifact.get("family", "atomic-memory"),
                                     artifact["artifact_id"], label_tags or ["untagged:true"])
        if new_status != current["status"]:
            self._write(KIND_PROGRESS, {
                "entity_id": f"prog_{uuid.uuid4().hex[:12]}", "seq": 1, "op": "progress",
                "note_id": note_id, "note_title": new_title, "note_seq": next_seq,
                "from_status": current["status"], "status": new_status,
                "memo": (reason or "")[:400], "at": stamp,
            })
        return {"id": note_id, "seq": next_seq, "chunks": chunks,
                "atomic_memory_ids": [(item.get("artifact") or {}).get("artifact_id") for item in written]}

    def set_note_status(self, note_id: str, status: str, memo: str = "") -> dict:
        if status not in NOTE_STATUSES:
            raise WorkbenchError("未知的进度状态", code="bad_status")
        return self.update_note(note_id, status=status, reason=memo)

    def retire_note(self, note_id: str) -> dict:
        notes = self.load()["notes"]
        existing = next((note for note in notes if note["id"] == note_id), None)
        if existing is None:
            raise WorkbenchError("找不到这条笔记", status=404, code="note_not_found")
        stamp = now()
        written = self._write(KIND_NOTE, {
            "entity_id": note_id, "seq": existing["seq"] + 1, "op": "retire",
            "title": existing["title"], "body": "", "course": existing["course"],
            "tags": existing["tags"], "keywords": existing["keywords"],
            "status": existing["status"], "created_at": existing["created_at"], "updated_at": stamp,
            "chunk_index": 0, "chunk_count": 1,
        })
        return {"id": note_id, "atomic_memory_id": (written[0].get("artifact") or {}).get("artifact_id")}

    def create_task(self, note_id: str, title: str) -> dict:
        title = str(title or "").strip()
        if not title:
            raise WorkbenchError("待办标题不能为空", code="title_required")
        if len(title) > 300:
            raise WorkbenchError("待办标题请控制在 300 字以内", code="title_too_long")
        stamp = now()
        entity_id = f"task_{uuid.uuid4().hex[:12]}"
        written = self._write(KIND_TASK, {
            "entity_id": entity_id, "seq": 1, "op": "create", "note_id": note_id, "title": title,
            "done": False, "created_at": stamp, "updated_at": stamp, "completed_at": None,
        }, description=title[:200])
        return {"id": entity_id, "atomic_memory_id": (written[0].get("artifact") or {}).get("artifact_id")}

    def set_task_done(self, task_id: str, done: bool) -> dict:
        tasks = {task["id"]: task for task in self.load()["tasks"]}
        existing = tasks.get(task_id)
        if existing is None:
            raise WorkbenchError("找不到这条待办", status=404, code="task_not_found")
        stamp = now()
        written = self._write(KIND_TASK, {
            "entity_id": task_id, "seq": existing["seq"] + 1, "op": "update", "note_id": existing["note_id"],
            "title": existing["title"], "done": bool(done), "created_at": existing["created_at"],
            "updated_at": stamp, "completed_at": stamp if done else None,
        }, description=existing["title"][:200])
        return {"id": task_id, "done": bool(done),
                "atomic_memory_id": (written[0].get("artifact") or {}).get("artifact_id")}

    def retire_task(self, task_id: str) -> dict:
        tasks = {task["id"]: task for task in self.load()["tasks"]}
        existing = tasks.get(task_id)
        if existing is None:
            raise WorkbenchError("找不到这条待办", status=404, code="task_not_found")
        stamp = now()
        written = self._write(KIND_TASK, {
            "entity_id": task_id, "seq": existing["seq"] + 1, "op": "retire", "note_id": existing["note_id"],
            "title": existing["title"], "done": existing["done"], "created_at": existing["created_at"],
            "updated_at": stamp, "completed_at": existing.get("completed_at"),
        })
        return {"id": task_id, "atomic_memory_id": (written[0].get("artifact") or {}).get("artifact_id")}

    # ----------------------------------------------------------------- searching

    def search(self, query: str, *, tags: list[str] | None = None, tag_match: str = "any",
               status: str | None = None, course: str | None = None) -> dict:
        """Retrieve from PowerContext, then fold. Reports which Server mechanism produced each hit."""
        query = str(query or "").strip()
        snapshot = self.load()
        notes = snapshot["notes"]
        provenance: dict[str, dict] = {}

        pc_hits: list[dict] = []
        search_error: str | None = None
        if query:
            try:
                found = self.client.search_atomic(self.scope_id, query, kind=KIND_NOTE, mode="text", limit=100)
                pc_hits = found.get("hits", [])
            except PCError as exc:
                search_error = exc.message

        # one Atomic Memory per revision and per chunk: map all of them back to their entity
        by_artifact: dict[str, str] = {}
        for note in notes:
            for artifact_id in note["atomic_memory_ids"]:
                by_artifact[artifact_id] = note["id"]

        for hit in pc_hits:
            artifact_id = (hit.get("memory", {}).get("artifact") or {}).get("artifact_id")
            entity = by_artifact.get(artifact_id)
            if entity is None:
                continue
            entry = provenance.setdefault(entity, {"via": [], "score": 0.0})
            entry["via"].extend(hit.get("matched_by") or ["text"])
            entry["score"] = max(entry["score"], float(hit.get("score") or 0.0))

        tag_filter_error: str | None = None
        tag_matched_records = 0
        wanted_tags = self._dedup([self._normalize_tag(tag) for tag in (tags or []) if tag])[:TAG_QUERY_MAX]
        if wanted_tags:
            try:
                records = self.client.list_atomic(self.scope_id, kind=KIND_NOTE, tags=wanted_tags,
                                                  tag_match=tag_match)
                tag_matched_records = len(records)
                for record in records:
                    entity = by_artifact.get((record.get("artifact") or {}).get("artifact_id"))
                    if entity:
                        entry = provenance.setdefault(entity, {"via": [], "score": 0.0})
                        entry["via"].append("tag")
            except PCError as exc:
                tag_filter_error = exc.message

        # PowerContext text search is token based, so a plain substring pass over the
        # folded current state runs too and is labelled separately in matched_via.
        if query:
            lowered = query.lower()
            for note in notes:
                haystack = " ".join([note["title"], note["body"], note["course"],
                                     " ".join(note["tags"]), " ".join(note["keywords"])]).lower()
                if lowered in haystack:
                    entry = provenance.setdefault(note["id"], {"via": [], "score": 0.0})
                    entry["via"].append("client-scan")

        filtering = bool(query or wanted_tags)
        results = []
        for note in notes:
            if filtering and note["id"] not in provenance:
                continue
            if status and note["status"] != status:
                continue
            if course and course.lower() not in note["course"].lower():
                continue
            info = provenance.get(note["id"], {"via": ["scope-list"], "score": 0.0})
            results.append(dict(note, matched_via=sorted(set(info["via"])), score=round(info["score"], 6)))
        results.sort(key=lambda item: item["updated_at"], reverse=True)
        results.sort(key=lambda item: item["score"], reverse=True)

        return {
            "query": query,
            "notes": results,
            "powercontext": {
                "search_hits": len(pc_hits),
                "search_mode": "text",
                "tag_filter": wanted_tags,
                "tag_match": tag_match,
                "tag_filter_records": tag_matched_records,
                "search_error": search_error,
                "tag_error": tag_filter_error,
            },
        }

    @staticmethod
    def _normalize_tag(tag: str) -> str:
        value = str(tag).strip()
        if ":" in value:
            return value
        return f"tag:{value}"

    @staticmethod
    def _dedup(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item and item not in seen:
                seen.add(item)
                out.append(item)
        return out

    # --------------------------------------------------------------- provenance

    def diagnostics(self) -> dict:
        info: dict[str, Any] = {}
        error = None
        try:
            info = self.client.server_info()
            # idempotent by contract: resolves to the existing Scope rather than duplicating it
            if self._scope_id is None:
                self.ensure_scope()
        except PCError as exc:
            error = exc.message
        return {
            "base_url": self.client.base_url,
            "reachable": bool(info),
            "error": error,
            "product": info.get("product"),
            "package_version": info.get("package_version"),
            "server_id": info.get("server_id"),
            "api_contract_version": info.get("api_contract_version"),
            "feature_contracts": sorted((info.get("feature_contracts") or {}).keys()),
            "scope_id": self._scope_id,
            "scope_idempotency_key": self.scope_key(),
            "kinds": list(KINDS),
            "recent_calls": [
                {"method": call.method, "path": call.path, "status": call.status,
                 "request_bytes": call.request_bytes, "response_bytes": call.response_bytes,
                 "duration_ms": call.duration_ms, "error": call.error}
                for call in self.client.trace[-12:]
            ],
        }
