"""Typed client for the PowerContext HTTP API used by 研习工作台.

Only the standard library is used so that the application adds no dependency on
top of the vendored PowerContext wheel. Every non-2xx answer raises PCError;
callers never see a silent empty result caused by a transport or API failure.
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterator

DEFAULT_URL = "http://127.0.0.1:2893"
MAX_TEXT_BYTES = 8192  # powercontext remember.text hard limit
SAFE_TEXT_BYTES = 7600  # headroom for the JSON envelope we embed in text
PAGE_LIMIT = 100
MAX_PAGES = 200


class PCError(Exception):
    """Any failure that means the requested PowerContext operation did not happen."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None,
                 details: Any = None, request_id: str | None = None, url: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.details = details
        self.request_id = request_id
        self.url = url

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "PowerContextError",
            "message": self.message,
            "status": self.status,
            "code": self.code,
            "details": self.details,
            "request_id": self.request_id,
            "url": self.url,
        }


class PCConfigError(PCError):
    pass


@dataclass
class CallRecord:
    """One observed request/response pair, kept for the in-app provenance panel."""

    method: str
    path: str
    status: int | None
    request_bytes: int
    response_bytes: int
    duration_ms: int
    items: int | None = None
    error: str | None = None


@dataclass
class PCClient:
    base_url: str = field(default_factory=lambda: os.environ.get("YANXI_PC_URL", DEFAULT_URL).rstrip("/"))
    timeout: float = float(os.environ.get("YANXI_PC_TIMEOUT", "20"))
    trace: list[CallRecord] = field(default_factory=list)

    # ---------------------------------------------------------------- transport

    def _request(self, method: str, path: str, payload: dict | None = None,
                 params: dict | None = None, extra_headers: dict | None = None) -> tuple[int, Any, dict]:
        url = self.base_url + path
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query:
                url = f"{url}?{query}"
        body = None
        headers = {"Accept": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        started = time.monotonic()
        status: int | None = None
        raw = b""
        try:
            request = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
                raw = response.read()
                response_headers = dict(response.headers)
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read() or b""
            response_headers = dict(exc.headers or {})
            self._record(method, path, status, body, raw, started, error="http_error")
            raise self._to_error(status, raw, response_headers, url) from exc
        except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            self._record(method, path, None, body, b"", started, error="transport")
            raise PCError(
                f"PowerContext service unreachable at {self.base_url}: {reason}",
                url=url,
            ) from exc
        self._record(method, path, status, body, raw, started)
        if not raw:
            return status, None, response_headers
        try:
            return status, json.loads(raw.decode("utf-8")), response_headers
        except (ValueError, UnicodeDecodeError) as exc:
            raise PCError(f"PowerContext returned a non-JSON body for {path}", status=status, url=url) from exc
        return status, None, response_headers

    @staticmethod
    def _to_error(status: int, raw: bytes, headers: dict, url: str) -> PCError:
        code = None
        message = None
        details = None
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
            err = parsed["error"]
            code = err.get("code")
            message = err.get("message")
            details = err.get("details")
        return PCError(
            message or f"PowerContext request failed with HTTP {status}",
            status=status,
            code=code,
            details=details,
            request_id=header_value(headers, "X-PowerContext-Request-ID"),
            url=url,
        )

    def _record(self, method, path, status, request_body, response_body, started, error=None, items=None):
        self.trace.append(
            CallRecord(
                method=method,
                path=path,
                status=status,
                request_bytes=len(request_body) if request_body else 0,
                response_bytes=len(response_body) if response_body else 0,
                duration_ms=int((time.monotonic() - started) * 1000),
                items=items,
                error=error,
            )
        )
        if len(self.trace) > 200:
            del self.trace[: len(self.trace) - 200]

    # ------------------------------------------------------------------- server

    def server_info(self) -> dict:
        _, data, _ = self._request("GET", "/v1/server-info")
        return data or {}

    def capabilities(self) -> dict:
        _, data, _ = self._request("GET", "/v1/capabilities")
        return data or {}

    # ------------------------------------------------------------------- scopes

    def list_scopes(self, query: str | None = None, query_field: str = "title", limit: int = 100) -> list[dict]:
        _, data, _ = self._request(
            "GET", "/v1/scopes", params={"query": query, "query_field": query_field, "limit": limit}
        )
        return (data or {}).get("items", [])

    def create_scope(self, title: str, summary: str, idempotency_key: str) -> dict:
        _, data, _ = self._request(
            "POST",
            "/v1/scopes",
            {"title": title, "summary": summary, "idempotency_key": idempotency_key},
        )
        if not data or "scope_id" not in data:
            raise PCError("PowerContext created a Scope without returning scope_id", code="missing_scope_id")
        return data

    # ----------------------------------------------------------- atomic memory

    def remember(self, scope_id: str, kind: str, text: str, *, description: str | None = None,
                 reason: str | None = None) -> list[dict]:
        payload: dict[str, Any] = {"scope_id": scope_id, "kind": kind, "text": text}
        if description:
            payload["description"] = description
        if reason:
            payload["reason"] = reason
        _, data, _ = self._request("POST", "/v1/memory/remember", payload)
        if not isinstance(data, dict) or "records" not in data:
            raise PCError("PowerContext remember returned no records", code="malformed_response")
        records = data["records"]
        if data.get("changed") is False and not records:
            raise PCError("PowerContext reported the write did not change anything", code="unchanged")
        return records

    def list_atomic(self, scope_id: str, *, kind: str | None = None, states: list[str] | None = None,
                    tags: list[str] | None = None, tag_match: str | None = None,
                    limit: int = PAGE_LIMIT) -> list[dict]:
        return list(self.iter_atomic(scope_id, kind=kind, states=states, tags=tags,
                                     tag_match=tag_match, limit=limit))

    def iter_atomic(self, scope_id: str, *, kind: str | None = None, states: list[str] | None = None,
                    tags: list[str] | None = None, tag_match: str | None = None,
                    limit: int = PAGE_LIMIT) -> Iterator[dict]:
        cursor = None
        for _ in range(MAX_PAGES):
            payload: dict[str, Any] = {"scope_id": scope_id, "limit": min(max(limit, 1), PAGE_LIMIT)}
            if kind is not None:
                payload["kind"] = kind
            if states:
                payload["states"] = states
            if tags:
                payload["tags"] = tags[:16]
                payload["tag_match"] = tag_match or "any"
            if cursor:
                payload["cursor"] = cursor
            _, data, _ = self._request("POST", "/v1/atomic-memory/list", payload)
            data = data or {}
            for item in data.get("items", []):
                yield item
            cursor = data.get("next_cursor")
            if not cursor:
                return
            if len(data.get("items", [])) == 0:
                raise PCError("PowerContext returned a cursor with no items", code="pagination_stall")
        raise PCError(
            f"Refusing to page beyond {MAX_PAGES} pages for kind={kind}", code="pagination_overflow"
        )

    def search_atomic(self, scope_id: str, query: str, *, kind: str | None = None,
                      tags: list[str] | None = None, mode: str = "text",
                      limit: int = 20) -> dict:
        payload: dict[str, Any] = {"scope_id": scope_id, "query": query[:MAX_TEXT_BYTES],
                                   "mode": mode, "limit": min(max(limit, 1), PAGE_LIMIT)}
        if kind:
            payload["kind"] = kind
        if tags:
            payload["tags"] = tags[:16]
        _, data, _ = self._request("POST", "/v1/atomic-memory/search", payload)
        if not isinstance(data, dict) or "hits" not in data:
            raise PCError("PowerContext search returned no hits array", code="malformed_response")
        return data

    # -------------------------------------------------------------------- tags

    def _tags_path(self, scope_id: str, family: str, artifact_id: str) -> str:
        return (f"/v1/scopes/{urllib.parse.quote(scope_id, safe='')}"
                f"/artifacts/{family}/{urllib.parse.quote(artifact_id, safe='')}/tags")

    def get_tags(self, scope_id: str, family: str, artifact_id: str) -> tuple[list[str], str | None]:
        """Return the tag set plus the ETag needed to replace it."""
        _, data, headers = self._request("GET", self._tags_path(scope_id, family, artifact_id))
        return (data or {}).get("tags", []), header_value(headers, "ETag")

    def replace_tags(self, scope_id: str, family: str, artifact_id: str, tags: list[str]) -> list[str]:
        """Replace labels under the Server's mandatory If-Match precondition.

        PowerContext requires an ETag here (HTTP 428 without one, 412 on a stale
        one), so read the current validator and retry once on a conflict.
        """
        cleaned = []
        for tag in tags[:32]:
            value = "".join(str(tag).split())
            if value:
                cleaned.append(value)
        path = self._tags_path(scope_id, family, artifact_id)
        for attempt in (1, 2):
            _, current, headers = self._request("GET", path)
            etag = header_value(headers, "ETag")
            if not etag:
                raise PCError("PowerContext returned no ETag for the artifact tag set", url=self.base_url + path)
            try:
                _, data, _ = self._request("PUT", path, {"tags": cleaned}, extra_headers={"If-Match": etag})
            except PCError as exc:
                if exc.status == 412 and attempt == 1:
                    continue
                raise
            return (data or {}).get("tags", cleaned)
        raise PCError("Artifact tags kept changing; giving up after 2 attempts", code="tag_conflict")


def header_value(headers: dict, name: str) -> str | None:
    """HTTP header names are case-insensitive; urllib's Message is, dict(headers) is not."""
    wanted = name.lower()
    for key, value in (headers or {}).items():
        if key.lower() == wanted:
            return value
    return None


def utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def chunk_text(text: str, max_bytes: int = SAFE_TEXT_BYTES) -> list[str]:
    """Split on character boundaries so no chunk exceeds max_bytes of UTF-8."""
    if not text:
        return [""]
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for char in text:
        char_size = utf8_len(char)
        if size + char_size > max_bytes and current:
            chunks.append("".join(current))
            current = []
            size = 0
        current.append(char)
        size += char_size
    if current:
        chunks.append("".join(current))
    return chunks
