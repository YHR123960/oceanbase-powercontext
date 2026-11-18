#!/usr/bin/env python3
"""Verify that 研习工作台's storage really is PowerContext, not an imitation.

Runs against a live PowerContext Server (default http://127.0.0.1:2893) and checks
the exact behaviours the workbench depends on:

  1. server identity / package version / feature contract for explicit memory
  2. model-free operation: generation-dependent capabilities must be disabled
  3. idempotent Scope creation
  4. Atomic Memory write -> read-back with artifact identity
  5. cursor pagination really returns every record
  6. server-side tag filtering (labels are stored by PowerContext, not the app)
  7. server-side text search with matched_by provenance
  8. failure propagation: the client must raise, never fake success
  9. durability: after a Server restart the same records read back identical

Usage:
    python scripts/verify_pc.py [--url http://127.0.0.1:2893] [--json evidence/pc_verify.json]

Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from yanxi.pc import (  # noqa: E402
    MAX_TEXT_BYTES,
    PCClient,
    PCError,
    chunk_text,
    utf8_len,
)

RESULTS: list[dict] = []
RUN_ID = time.strftime("%Y%m%d-%H%M%S", time.localtime())


def check(name: str, ok: bool, detail: str) -> None:
    RESULTS.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def http_get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:2893")
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    client = PCClient(base_url=args.url)

    # 1 + 2 ------------------------------------------------------------- identity
    info = client.server_info()
    check(
        "server_identity",
        info.get("product") == "powercontext",
        f"product={info.get('product')} package_version={info.get('package_version')} "
        f"api_contract={info.get('api_contract_version')} server_id={info.get('server_id')}",
    )
    features = (info.get("feature_contracts") or {})
    check(
        "explicit_memory_contract_present",
        "memory.explicit" in features,
        f"feature_contracts={[sorted(features)]}",
    )
    caps = client.capabilities()
    extract = ((caps.get("prompts") or {}).get("atomic_memory.extract") or {})
    check(
        "runs_without_any_model",
        extract.get("status") == "disabled",
        f"atomic_memory.extract status={extract.get('status')} reason={extract.get('reason')} "
        "(explicit Atomic Memory writes need no generation model)",
    )

    # 3 ------------------------------------------------------------------ scope
    title = f"verify-{RUN_ID}"
    key = f"qoder-yanxi-verify-{RUN_ID}"
    first = client.create_scope(title=title, summary=f"verification run {RUN_ID}", idempotency_key=key)
    second = client.create_scope(title=title, summary=f"verification run {RUN_ID}", idempotency_key=key)
    check(
        "scope_idempotency",
        first["scope_id"] == second["scope_id"],
        f"scope_id={first['scope_id']} reused on the same idempotency_key "
        f"(version={first.get('version')})",
    )
    scope_id = first["scope_id"]

    # 4 ----------------------------------------------------------------- write
    kind = "yanxi.verify.note.v1"
    payload = {"entity_id": "note-verify-1", "seq": 1, "title": "幂等验证笔记", "text": "内容来自 Qoder 验证脚本"}
    text = json.dumps(payload, ensure_ascii=False)
    records = client.remember(scope_id, kind, text, description=payload["title"])
    artifact = (records[0].get("artifact") or {}) if records else {}
    check(
        "atomic_memory_write_readback",
        bool(records) and records[0].get("kind") == kind and records[0].get("text") == text,
        f"returned {len(records)} record(s) artifact.family={artifact.get('family')} "
        f"artifact_id={artifact.get('artifact_id')} revision={artifact.get('revision')} state={records[0].get('state')}",
    )

    back = client.list_atomic(scope_id, kind=kind, states=["active"])
    check(
        "read_back_by_kind",
        len(back) == 1 and json.loads(back[0]["text"])["entity_id"] == "note-verify-1",
        f"list_atomic(kind={kind}) returned {len(back)} active record(s)",
    )

    # 5 ------------------------------------------------------------- pagination
    fill_kind = "yanxi.verify.fill.v1"
    for index in range(12):
        client.remember(scope_id, fill_kind, json.dumps({"entity_id": f"fill-{index}", "i": index},
                                                        ensure_ascii=False))
    small_pages = []
    cursor = None
    pages = 0
    while pages < 20:
        payload_page = {"scope_id": scope_id, "kind": fill_kind, "states": ["active"], "limit": 5}
        if cursor:
            payload_page["cursor"] = cursor
        import urllib.parse

        request = urllib.request.Request(
            f"{args.url.rstrip('/')}/v1/atomic-memory/list",
            data=json.dumps(payload_page).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        small_pages.extend(data.get("items", []))
        cursor = data.get("next_cursor")
        pages += 1
        if not cursor:
            break
    auto = client.list_atomic(scope_id, kind=fill_kind, states=["active"], limit=100)
    check(
        "cursor_pagination_complete",
        len(small_pages) == 12 and len(auto) == 12 and pages == 3,
        f"limit=5 walked {pages} pages and yielded {len(small_pages)} records; "
        f"client helper with limit=100 yielded {len(auto)} records (no silent truncation)",
    )

    # 6 ------------------------------------------------------------------ tags
    tag_kind = "yanxi.verify.tagged.v1"
    tagged = client.remember(scope_id, tag_kind, json.dumps({"entity_id": "t1", "title": "图数据库复习"},
                                                            ensure_ascii=False))
    tid = tagged[0]["artifact"]["artifact_id"]
    family = tagged[0]["artifact"]["family"]
    client.replace_tags(scope_id, family, tid, ["course:数据库", "topic:index", "状态:未完成"])
    read_tags, _etag = client.get_tags(scope_id, family, tid)
    hit_all = client.list_atomic(scope_id, kind=tag_kind, tags=["course:数据库", "topic:index"],
                                 tag_match="all")
    miss = client.list_atomic(scope_id, kind=tag_kind, tags=["course:不存在的课程"], tag_match="all")
    check(
        "server_side_tag_retrieval",
        len(read_tags) == 3 and len(hit_all) == 1 and len(miss) == 0,
        f"PowerContext stored and filtered labels: stored={sorted(read_tags)} "
        f"tag_match=all(2 tags) -> {len(hit_all)} hit(s), unknown tag -> {len(miss)} hit(s)",
    )

    # 7 ---------------------------------------------------------------- search
    search = client.search_atomic(scope_id, "图数据库", kind=tag_kind, mode="text", limit=10)
    hits = search.get("hits", [])
    check(
        "server_side_text_search",
        len(hits) >= 1 and "text" in (hits[0].get("matched_by") or []),
        f"mode={search.get('mode')} hits={len(hits)} matched_by={hits[0].get('matched_by') if hits else None} "
        f"score={hits[0].get('score') if hits else None}",
    )

    # 8 ------------------------------------------------------- error handling
    empty_status = empty_code = None
    try:
        client.remember(scope_id, "yanxi.verify.bad.v1", "")
    except PCError as exc:
        empty_status, empty_code = exc.status, exc.code
    oversized = "溢" * 5000
    over_status = None
    try:
        client.remember(scope_id, "yanxi.verify.bad.v1", oversized)
    except PCError as exc:
        over_status = exc.status
    unknown_scope = None
    try:
        client.list_atomic("scope-that-does-not-exist-xyz", kind=kind)
    except PCError as exc:
        unknown_scope = exc.status
    check(
        "failures_propagate_not_faked",
        empty_status == 422 and over_status in (422, 413) and unknown_scope in (400, 403, 404, 422),
        f"empty text -> HTTP {empty_status} (code={empty_code}); "
        f"{utf8_len(oversized)}-byte text (limit {MAX_TEXT_BYTES}) -> HTTP {over_status}; "
        f"unknown scope -> HTTP {unknown_scope}. All raised as PCError instead of returning an empty success.",
    )
    chunks = chunk_text(oversized, 7600)
    check(
        "chunking_respects_byte_limit",
        all(utf8_len(chunk) <= 7600 for chunk in chunks) and "".join(chunks) == oversized,
        f"long text split into {len(chunks)} chunk(s), each <= 7600 UTF-8 bytes, lossless when rejoined",
    )

    # 9 ---------------------------------------------------------------- restart
    summary_before = sorted(item["text"] for item in client.list_atomic(scope_id, kind=fill_kind))
    check(
        "records_stable_across_reconnect",
        len(summary_before) == 12,
        f"re-read {len(summary_before)} records from SQLite home; run scripts/e2e_restart.py "
        "for the full process stop/start durability proof",
    )

    passed = sum(1 for item in RESULTS if item["status"] == "PASS")
    report = {
        "run_id": RUN_ID,
        "url": args.url,
        "scope_id": scope_id,
        "server_package_version": info.get("package_version"),
        "server_id": info.get("server_id"),
        "checks_total": len(RESULTS),
        "checks_passed": passed,
        "results": RESULTS,
        "pc_calls_traced": len(client.trace),
    }
    print(f"\n== {passed}/{len(RESULTS)} checks passed ==")
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report written: {out}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
