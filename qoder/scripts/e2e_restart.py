#!/usr/bin/env python3
"""Prove durability the way a reviewer would check it: write, kill both processes, restart, compare.

The script owns its own workspace and application port, so it never disturbs a demo that is
already running. It performs a real PowerContext Server restart through scripts/start_pc.sh.

    python scripts/e2e_restart.py [--pc-url http://127.0.0.1:2893] [--app-port 2899]
                                  [--workspace e2e] [--json evidence/e2e_restart.json]

Exit code 0 only when every stage passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from yanxi.pc import PCClient  # noqa: E402
from yanxi.store import KIND_NOTE, KIND_PROGRESS, KIND_TASK, Workbench  # noqa: E402

WSL_DISTRO = os.environ.get("YANXI_WSL_DISTRO", "Ubuntu-22.04")
WHEEL_SHA = "cd9ef57783eed3689b69be829003b649e0ac6c09ec05b2ed679424191de0aa14"

STEPS: list[dict] = []
LONG_BODY = "注意力机制的三种失败模式：" + "长程依赖、位置外推、稀疏注意的近似误差。" * 260


def step(name: str, ok: bool, detail: str) -> None:
    STEPS.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def to_linux_path(win_path: Path) -> str:
    """D:\\a\\b -> /mnt/a/b without round-tripping through wslpath (wsl.exe emits UTF-16)."""
    text = str(win_path).replace("\\", "/")
    if len(text) > 1 and text[1] == ":":
        return f"/mnt/{text[0].lower()}/{text[2:].lstrip('/')}"
    return text


def wsl_script(script: str, *args: str) -> subprocess.CompletedProcess:
    """Run one of the project's WSL shell scripts from Windows."""
    linux_root = to_linux_path(ROOT)
    command = ["wsl.exe", "-d", WSL_DISTRO, "--", "bash", f"{linux_root}/scripts/{script}", *args]
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def snapshot_pc(client: PCClient, scope_id: str) -> dict:
    """Raw records straight from PowerContext, independent of the application layer."""
    out: dict[str, str] = {}
    for kind in (KIND_NOTE, KIND_TASK, KIND_PROGRESS):
        records = client.list_atomic(scope_id, kind=kind, states=["active"])
        body = "\n".join(sorted(f"{item['artifact']['artifact_id']}|{item['kind']}|{item['text']}"
                                for item in records))
        out[kind] = digest(body)
        out[f"{kind}::count"] = str(len(records))
    return out


def get_json(url: str, timeout: float = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def start_app(port: int, workspace: str, pc_url: str):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONIOENCODING": "utf-8"}
    log = open(ROOT / ".runtime" / "e2e-app.log", "w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "yanxi.server", "--host", "127.0.0.1", "--port", str(port),
         "--workspace", workspace, "--pc-url", pc_url],
        cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"application exited during startup (code {process.returncode})")
        try:
            get_json(f"http://127.0.0.1:{port}/api/health", timeout=2)
            return process, log
        except (urllib.error.URLError, OSError):
            time.sleep(0.4)
    process.kill()
    raise RuntimeError("application readiness timeout")


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pc-url", default="http://127.0.0.1:2893")
    parser.add_argument("--app-port", type=int, default=2899)
    parser.add_argument("--workspace", default="e2e")
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    app_base = f"http://127.0.0.1:{args.app_port}"
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    marker = f"e2e-{time.strftime('%H%M%S')}"
    (ROOT / ".runtime").mkdir(exist_ok=True)

    # 1 - the PowerContext Server must already be up ------------------------------------
    client = PCClient(base_url=args.pc_url)
    try:
        info = client.server_info()
    except Exception as exc:  # noqa: BLE001 - reported to the user verbatim
        print(f"PowerContext 不可用（{exc}）。先运行 bash scripts/start_pc.sh", file=sys.stderr)
        return 2
    step("service_available", info.get("product") == "powercontext",
         f"package={info.get('package_version')} server_id={info.get('server_id')}")

    # 2 - write through the application, not directly -----------------------------------
    app, log = start_app(args.app_port, args.workspace, args.pc_url)
    scope_id = get_json(f"{app_base}/api/health")["data"]["scope_id"]
    note_a = post_json(f"{app_base}/api/notes", {
        "title": f"{marker} 阅读：检索增强生成的引用可靠性",
        "body": "预印本版本结论与后续评审版不一致，需以正式版本为准。",
        "course": "科研阅读", "tags": "RAG,引用核查", "keywords": "preprint",
    })["data"]
    note_b = post_json(f"{app_base}/api/notes", {
        "title": f"{marker} 课程：索引选择率与统计信息", "body": LONG_BODY, "course": "数据库",
        "tags": "索引", "keywords": "选择率",
    })["data"]
    task = post_json(f"{app_base}/api/tasks", {"note_id": note_a["id"], "title": "找出正式发表版本并对照实验表"})["data"]
    post_json(f"{app_base}/api/notes/{note_a['id']}/status", {"status": "reading", "memo": "已读完方法节"})
    post_json(f"{app_base}/api/tasks/{task['id']}/done", {"done": True})

    before_state = get_json(f"{app_base}/api/state")["data"]
    mine = [item for item in before_state["notes"] if marker in item["title"]]
    chunks = next(item["chunks"] for item in mine if item["id"] == note_b["id"])
    step("write_through_application", len(mine) == 2 and chunks > 1,
         f"2 notes created via HTTP, long note stored in {chunks} Atomic Memory chunks "
         f"(body {len(LONG_BODY.encode('utf-8'))} bytes); task closed; progress recorded")

    # 3 - the same data must be visible without the application at all -----------------
    pc_only = snapshot_pc(client, scope_id)
    direct = Workbench(PCClient(base_url=args.pc_url), workspace=args.workspace)
    direct_titles = [item["title"] for item in direct.load()["notes"] if marker in item["title"]]
    step("readable_without_the_app", sorted(direct_titles) == sorted(item["title"] for item in mine),
         f"PowerContext alone (scope {scope_id}) answers with {len(direct_titles)} records of this run")

    before_app = digest(json.dumps(before_state, ensure_ascii=False, sort_keys=True))

    # 4 - kill both processes -----------------------------------------------------------
    app.kill()
    app.wait(timeout=20)
    log.close()
    stopped = wsl_script("start_pc.sh", "stop")
    step("processes_stopped", "stopped" in stopped.stdout or "not running" in stopped.stdout,
         f"app pid terminated; start_pc.sh stop -> {stopped.stdout.strip()[:60]}")
    time.sleep(1.5)
    try:
        get_json(f"{args.pc_url}/v1/server-info", timeout=2)
        reachable = True
    except (urllib.error.URLError, OSError):
        reachable = False
    step("service_really_went_down", not reachable,
         f"/v1/server-info after stop: {'still reachable' if reachable else 'connection refused'}")

    # 5 - bring the Server back from disk -----------------------------------------------
    started_again = wsl_script("start_pc.sh", "start")
    ready = "ready" in started_again.stdout
    step("service_restarted", ready,
         started_again.stdout.strip().splitlines()[0] if started_again.stdout else started_again.stderr[:200])
    if not ready:
        return 1

    app2, log2 = start_app(args.app_port, args.workspace, args.pc_url)
    after_state = get_json(f"{app_base}/api/state")["data"]
    after_info = get_json(f"{app_base}/api/pc")["data"]

    after_pc = snapshot_pc(client, after_info["scope_id"])
    same_records = all(after_pc[key] == pc_only[key] for key in pc_only)
    step("powercontext_records_identical_after_restart", same_records,
         "; ".join(f"{key.split('::')[-1] if '::' in key else key.split('.')[-1]}={after_pc[key]}"
                   for key in pc_only))
    step("scope_reused_after_restart", after_info["scope_id"] == scope_id,
         f"idempotency_key {after_info['scope_idempotency_key']} resolved the same Scope")

    after_mine = [item for item in after_state["notes"] if marker in item["title"]]
    restored_ok = (
        len(after_mine) == 2
        and next(item["body"] for item in after_mine if item["id"] == note_b["id"]) == LONG_BODY
        and next(item["status"] for item in after_mine if item["id"] == note_a["id"]) == "reading"
        and any(item["id"] == task["id"] and item["done"] for item in after_state["tasks"])
    )
    step("application_state_restored", restored_ok,
         "long-text note reassembled byte-for-byte, progress 'reading' and the completed task came back")

    reuse = post_json(f"{app_base}/api/notes/{note_a['id']}/status",
                      {"status": "mastered", "memo": "复用重启后的记忆继续推进"})["data"]
    final = get_json(f"{app_base}/api/state")["data"]
    final_note = next(item for item in final["notes"] if item["id"] == note_a["id"])
    events = [item for item in final["progress"] if item["note_id"] == note_a["id"]]
    step("memory_reused_for_continuation", reuse["seq"] == final_note["seq"] == 3 and len(events) == 2,
         f"seq {reuse['seq']} built on the pre-restart history; timeline has {len(events)} progress memories")

    app2.kill()
    app2.wait(timeout=20)
    log2.close()

    passed = sum(1 for item in STEPS if item["status"] == "PASS")
    report = {
        "started_at": started,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "marker": marker,
        "workspace": args.workspace,
        "pc_url": args.pc_url,
        "app_port": args.app_port,
        "scope_id": scope_id,
        "package_version": info.get("package_version"),
        "server_id": info.get("server_id"),
        "wheel_sha256": WHEEL_SHA,
        "powercontext_snapshot_before": pc_only,
        "powercontext_snapshot_after": after_pc,
        "app_state_digest_before_restart": before_app,
        "app_state_digest_after_restart": digest(json.dumps(after_state, ensure_ascii=False, sort_keys=True)),
        "long_body_bytes": len(LONG_BODY.encode("utf-8")),
        "long_body_chunks": chunks,
        "steps_total": len(STEPS),
        "steps_passed": passed,
        "results": STEPS,
        "environment": {"python": sys.version.split()[0], "platform": sys.platform,
                        "wsl_distro": WSL_DISTRO, "bash": shutil.which("bash")},
    }
    print(f"\n== {passed}/{len(STEPS)} steps passed ==")
    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"report written: {out}")
    return 0 if passed == len(STEPS) else 1


if __name__ == "__main__":
    sys.exit(main())
