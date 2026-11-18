"""In-memory stand-in for the slice of PowerContext that the workbench uses.

It reproduces the behaviours the application depends on - the 8192-byte text limit,
mandatory If-Match on tag replacement, kind/state/tag filtering and cursor pagination -
so the domain logic can be unit-tested without a running Server.
`tests/test_live_powercontext.py` asserts the same expectations against the real service.
"""

from __future__ import annotations

import itertools
import json
import urllib.parse

from yanxi.pc import CallRecord, MAX_TEXT_BYTES, PCError

# The stand-in raises the same exception type as the real client, so callers exercise
# their genuine error handling instead of a test-only branch.
FakePCError = PCError


class FakePowerContext:
    """Duck-typed replacement for yanxi.pc.PCClient."""

    def __init__(self, base_url: str = "http://fake", **_kwargs):
        self.base_url = base_url
        self.trace: list[CallRecord] = []
        self.scopes: dict[str, dict] = {}
        self.memories: list[dict] = []
        self.tags: dict[str, list[str]] = {}
        self.server_id = "fake-server"
        self._ids = itertools.count(1)
        self.fail_next_write = False

    # ------------------------------------------------------------------ server

    def server_info(self) -> dict:
        return {"product": "powercontext", "package_version": "fake", "server_id": self.server_id,
                "api_contract_version": {"major": 1, "minor": 5},
                "feature_contracts": {"memory.explicit": {}, "scope.selection": {}}}

    def capabilities(self) -> dict:
        return {"prompts": {"atomic_memory.extract": {"status": "disabled",
                                                     "reason": "provider_not_configured"}}}

    # ------------------------------------------------------------------ scopes

    def create_scope(self, title: str, summary: str, idempotency_key: str) -> dict:
        existing = self.scopes.get(idempotency_key)
        if existing:
            return dict(existing)
        descriptor = {"scope_id": f"scp_fake_{next(self._ids)}", "title": title, "summary": summary,
                      "version": 1, "idempotency_key": idempotency_key}
        self.scopes[idempotency_key] = descriptor
        return dict(descriptor)

    def list_scopes(self, query=None, query_field="title", limit=100) -> list[dict]:
        return [dict(item) for item in self.scopes.values()]

    # --------------------------------------------------------- atomic memory

    def remember(self, scope_id: str, kind: str, text: str, *, description=None, reason=None) -> list[dict]:
        if self.fail_next_write:
            self.fail_next_write = False
            raise FakePCError("simulated PowerContext outage", status=503, code="unavailable")
        if not any(item["scope_id"] == scope_id for item in self.scopes.values()):
            raise FakePCError("Scope not found", status=404, code="not_found")
        if not kind or not text:
            raise FakePCError("invalid request", status=422, code="invalid_request")
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise FakePCError("text exceeds 8192 UTF-8 bytes", status=422, code="invalid_request")
        artifact_id = f"art_fake_{next(self._ids)}"
        record = {"artifact": {"family": "atomic-memory", "artifact_id": artifact_id, "revision": 1},
                  "kind": kind, "text": text, "state": "active", "state_version": 1,
                  "merged_into_id": None, "description": description}
        self.memories.append(record)
        return [record]

    def list_atomic(self, scope_id: str, *, kind=None, states=None, tags=None, tag_match=None,
                    limit=100) -> list[dict]:
        wanted = set(states or ["active"])
        wanted_tags = set(tags or [])
        out = []
        for record in self.memories:
            if kind is not None and record["kind"] != kind:
                continue
            if record["state"] not in wanted:
                continue
            if wanted_tags:
                stored = set(self.tags.get(record["artifact"]["artifact_id"], []))
                if tag_match == "all":
                    if not wanted_tags.issubset(stored):
                        continue
                elif not wanted_tags & stored:
                    continue
            out.append(record)
        return [dict(record) for record in out][:limit]

    def search_atomic(self, scope_id: str, query: str, *, kind=None, tags=None, mode="text",
                      limit=20) -> dict:
        hits = []
        needle = query.lower()
        for record in self.list_atomic(scope_id, kind=kind, tags=tags, states=["active"], limit=100):
            if needle and needle not in record["text"].lower():
                continue
            hits.append({"memory": record, "score": 0.5, "matched_by": [mode]})
            if len(hits) >= limit:
                break
        return {"mode": mode, "hits": hits}

    # -------------------------------------------------------------------- tags

    def replace_tags(self, scope_id: str, family: str, artifact_id: str, tags: list[str]) -> list[str]:
        if artifact_id not in {item["artifact"]["artifact_id"] for item in self.memories}:
            raise FakePCError("artifact not found", status=404, code="not_found")
        cleaned = [value for value in ("".join(str(tag).split()) for tag in tags) if value]
        for value in cleaned:
            if len(value) > 64:
                raise FakePCError("tag too long", status=422, code="invalid_request")
        self.tags[artifact_id] = cleaned
        return cleaned

    def get_tags(self, scope_id: str, family: str, artifact_id: str) -> tuple[list[str], str]:
        return list(self.tags.get(artifact_id, [])), f'W"{artifact_id}"'

    # -------------------------------------------------------------- inspection

    def records_for(self, kind: str) -> list[dict]:
        return [item for item in self.memories if item["kind"] == kind]

    def payloads_for(self, kind: str) -> list[dict]:
        return [json.loads(item["text"]) for item in self.records_for(kind)]
