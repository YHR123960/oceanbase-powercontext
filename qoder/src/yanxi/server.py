"""HTTP layer for 研习工作台: a dependency-free stdlib server in front of PowerContext.

Every request builds a fresh PowerContext client and re-reads state from the Server, so
the application holds no cache that could masquerade as persistence.

Usage:
    python -m yanxi.server --port 2894 [--host 127.0.0.1] [--workspace default]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __package__ in (None, ""):  # allow `python src/yanxi/server.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from .pc import PCClient, PCError  # noqa: E402
from .store import Workbench, WorkbenchError  # noqa: E402

WEB_ROOT = (Path(__file__).resolve().parents[2] / "web").resolve()
MAX_BODY = 1_500_000
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

_config = {"workspace": os.environ.get("YANXI_WORKSPACE", "default"),
           "pc_url": os.environ.get("YANXI_PC_URL", "http://127.0.0.1:2893")}


def _split_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，;；]", value) if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


class Handler(BaseHTTPRequestHandler):
    server_version = "YanxiWorkbench/0.1"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------- plumbing

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str, **extra) -> None:
        payload = {"ok": False, "error": {"code": code, "message": message}}
        payload.update(extra)
        self._send_json(status, payload)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise WorkbenchError(f"请求体 {length} 字节超过上限 {MAX_BODY}", status=413, code="body_too_large")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise WorkbenchError(f"请求体不是合法 JSON：{exc}", code="bad_json") from exc
        if not isinstance(data, dict):
            raise WorkbenchError("请求体必须是 JSON 对象", code="bad_json")
        return data

    def _workbench(self) -> Workbench:
        client = PCClient(base_url=_config["pc_url"])
        return Workbench(client, workspace=_config["workspace"])

    # ---------------------------------------------------------------- routes

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            return self._serve_file("index.html")
        if path.startswith("/static/"):
            return self._serve_file(path[len("/static/"):])
        if path == "/api/health":
            return self._handle_health()
        if path == "/api/state":
            return self._handle(lambda wb: wb.load())
        if path == "/api/search":
            terms = {key: (query.get(key) or [""])[0] for key in ("q", "tags", "match", "status", "course")}
            return self._handle(lambda wb: wb.search(
                terms["q"],
                tags=_split_list(terms["tags"]),
                tag_match="all" if terms["match"] == "all" else "any",
                status=terms.get("status") or None,
                course=terms.get("course") or None,
            ))
        if path == "/api/pc":
            return self._handle(lambda wb: {**wb.diagnostics(), "workspace": _config["workspace"]})
        return self._error(404, "not_found", f"未知路径 {path}")

    def do_POST(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        try:
            payload = self._read_json()
        except WorkbenchError as exc:
            return self._error(exc.status, exc.code, exc.message)

        if path == "/api/notes":
            return self._handle(lambda wb: wb.create_note(
                title=payload.get("title", ""),
                body=payload.get("body", ""),
                course=payload.get("course", ""),
                tags=_split_list(payload.get("tags")),
                keywords=_split_list(payload.get("keywords")),
            ))
        match = re.fullmatch(r"/api/notes/([^/]+)/status", path)
        if match:
            return self._handle(lambda wb: wb.set_note_status(
                urllib.parse.unquote(match.group(1)),
                str(payload.get("status", "")),
                str(payload.get("memo", "")),
            ))
        match = re.fullmatch(r"/api/notes/([^/]+)", path)
        if match:
            note_id = urllib.parse.unquote(match.group(1))
            fields = {key: payload[key] for key in ("title", "body", "course", "tags", "keywords", "status")
                      if key in payload}
            if "tags" in fields:
                fields["tags"] = _split_list(fields["tags"])
            if "keywords" in fields:
                fields["keywords"] = _split_list(fields["keywords"])
            return self._handle(lambda wb: wb.update_note(note_id, reason=str(payload.get("reason", "")),
                                                          **fields))
        if path == "/api/tasks":
            return self._handle(lambda wb: wb.create_task(str(payload.get("note_id", "")),
                                                          payload.get("title", "")))
        match = re.fullmatch(r"/api/tasks/([^/]+)/done", path)
        if match:
            return self._handle(lambda wb: wb.set_task_done(urllib.parse.unquote(match.group(1)),
                                                            bool(payload.get("done", True))))
        return self._error(404, "not_found", f"未知路径 {path}")

    def do_PATCH(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        try:
            payload = self._read_json()
        except WorkbenchError as exc:
            return self._error(exc.status, exc.code, exc.message)
        match = re.fullmatch(r"/api/notes/([^/]+)", path)
        if match:
            note_id = urllib.parse.unquote(match.group(1))
            fields = {key: payload[key] for key in ("title", "body", "course", "tags", "keywords", "status")
                      if key in payload}
            if "tags" in fields:
                fields["tags"] = _split_list(fields["tags"])
            if "keywords" in fields:
                fields["keywords"] = _split_list(fields["keywords"])
            return self._handle(lambda wb: wb.update_note(note_id, reason=str(payload.get("reason", "")),
                                                          **fields))
        return self._error(404, "not_found", f"未知路径 {path}")

    def do_DELETE(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        match = re.fullmatch(r"/api/notes/([^/]+)", path)
        if match:
            return self._handle(lambda wb: wb.retire_note(urllib.parse.unquote(match.group(1))))
        match = re.fullmatch(r"/api/tasks/([^/]+)", path)
        if match:
            return self._handle(lambda wb: wb.retire_task(urllib.parse.unquote(match.group(1))))
        return self._error(404, "not_found", f"未知路径 {path}")

    # ------------------------------------------------------------- execution

    def _handle(self, action) -> None:
        workbench = self._workbench()
        try:
            data = action(workbench)
        except WorkbenchError as exc:
            return self._error(exc.status, exc.code, exc.message)
        except PCError as exc:
            return self._error(502, "powercontext_error", exc.message,
                               powercontext=exc.to_dict(),
                               hint="PowerContext 未确认该操作，数据未被修改。请检查服务是否运行："
                                    "bash scripts/start_pc.sh status")
        except Exception as exc:  # pragma: no cover - unexpected defects must stay visible
            return self._error(500, "internal_error", f"{type(exc).__name__}: {exc}")
        return self._send_json(200, {"ok": True, "data": data,
                                     "pc_calls": len(workbench.client.trace)})

    def _handle_health(self) -> None:
        workbench = self._workbench()
        try:
            info = workbench.client.server_info()
            workbench.ensure_scope()
            return self._send_json(200, {
                "ok": True,
                "data": {"powercontext": {"reachable": True,
                                          "product": info.get("product"),
                                          "package_version": info.get("package_version"),
                                          "server_id": info.get("server_id")},
                         "scope_id": workbench._scope_id,
                         "workspace": _config["workspace"]},
            })
        except PCError as exc:
            return self._error(503, "powercontext_unreachable", exc.message, powercontext=exc.to_dict())

    def _serve_file(self, relative: str) -> None:
        candidate = (WEB_ROOT / relative).resolve()
        if not str(candidate).startswith(str(WEB_ROOT)) or not candidate.is_file():
            return self._error(404, "not_found", f"缺少静态文件 {relative}")
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(candidate.suffix.lower(),
                                                           "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="研习工作台 local server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("YANXI_PORT", "2894")))
    parser.add_argument("--workspace", default=_config["workspace"])
    parser.add_argument("--pc-url", default=_config["pc_url"])
    args = parser.parse_args()

    _config["workspace"] = args.workspace
    _config["pc_url"] = args.pc_url

    probe = Workbench(PCClient(base_url=args.pc_url), workspace=args.workspace)
    try:
        scope_id = probe.ensure_scope()
        info = probe.client.server_info()
    except PCError as exc:
        print(f"无法连接 PowerContext：{exc.message}", file=sys.stderr)
        print("先启动服务：bash scripts/start_pc.sh", file=sys.stderr)
        return 1
    print(f"PowerContext {info.get('package_version')} server_id={info.get('server_id')}")
    print(f"Scope={scope_id}  workspace={args.workspace}")
    print(f"研习工作台 http://{args.host}:{args.port}")

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
