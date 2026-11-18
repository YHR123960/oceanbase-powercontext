"""Auditable SDD workflow; no synthetic provider evidence."""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def audit(event, **data):
    directory = Path(os.environ.get("SDD_EVIDENCE", ROOT / "evidence"))
    directory.mkdir(parents=True, exist_ok=True)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    record = {"time": datetime.now(timezone.utc).isoformat(), "event": event,
              "command": sys.argv, "revision": revision, **data}
    serialized = json.dumps(record, ensure_ascii=False)
    for name in ("MINIMAX_API_KEY", "POWERCONTEXT_TOKEN", "SDD_DB_PASSWORD"):
        secret = os.environ.get(name)
        if secret: serialized = serialized.replace(secret, "[REDACTED]")
    record = json.loads(serialized)
    with (directory / "events.jsonl").open("a", encoding="utf8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record

class Store:
    """Dedicated MySQL-protocol database. Requires a real seekdb/OceanBase server."""
    def __init__(self):
        import pymysql
        self.db = os.environ.get("SDD_DATABASE", "minimax_sdd_2026")
        if not re.fullmatch(r"minimax_sdd_[A-Za-z0-9_]+", self.db):
            raise ValueError("SDD_DATABASE must start with minimax_sdd_ and contain safe SQL identifier characters")
        self.conn = pymysql.connect(host=os.environ.get("SDD_DB_HOST", "127.0.0.1"),
            port=int(os.environ.get("SDD_DB_PORT", "2881")), user=os.environ.get("SDD_DB_USER", "root"),
            password=os.environ.get("SDD_DB_PASSWORD", ""), charset="utf8mb4", autocommit=False,
            connect_timeout=5, cursorclass=pymysql.cursors.DictCursor)
        identity = self.sql("SELECT VERSION() AS version, @@version_comment AS comment", fetch=True)
        if not any(x in json.dumps(identity).lower() for x in ("oceanbase", "seekdb")):
            raise RuntimeError("Refusing a database not identified as seekdb/OceanBase")
        self.sql(f"CREATE DATABASE IF NOT EXISTS `{self.db}`")
        self.sql(f"USE `{self.db}`")
        self.sql("CREATE TABLE IF NOT EXISTS documents (path VARCHAR(255) NOT NULL, kind VARCHAR(16) NOT NULL, task VARCHAR(128) NOT NULL, sha CHAR(64) NOT NULL, content LONGTEXT NOT NULL, active BOOLEAN NOT NULL, PRIMARY KEY(path,sha))")
        self.conn.commit()

    def sql(self, query, args=None, fetch=False):
        with self.conn.cursor() as c:
            c.execute(query, args)
            result = c.fetchall() if fetch else {"affected": c.rowcount}
        audit("sql", sql=query, params=args, result=result, exit_code=0)
        return result

    def ingest(self, relative, kind, task):
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or kind not in ("spec", "code", "target", "regression"):
            raise ValueError("Invalid source path or kind")
        body = path.read_text(encoding="utf8")
        source = path.relative_to(ROOT).as_posix()
        try:
            self.sql("UPDATE documents SET active=FALSE WHERE path=%s", (source,))
            self.sql("INSERT INTO documents(path,kind,task,sha,content,active) VALUES(%s,%s,%s,%s,%s,TRUE) ON DUPLICATE KEY UPDATE active=TRUE,kind=VALUES(kind),task=VALUES(task)", (source,kind,task,digest(body),body))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return {"path": source, "sha": digest(body)}

    def context(self, task):
        rows = self.sql("SELECT path,kind,sha,content FROM documents WHERE active=TRUE AND task=%s ORDER BY kind,path", (task,), True)
        if {r["kind"] for r in rows} != {"spec", "code", "target", "regression"}:
            raise ValueError("Context requires current spec, code, target and regression sources")
        return {"task_id": task, "sources": rows}

class PowerContext:
    """Official HTTP contracts inspected at 437aa063264be8081fc9d032c7dde7df7995f694."""
    def call(self, endpoint, payload):
        base = os.environ["POWERCONTEXT_URL"].rstrip("/")
        headers = {"Content-Type": "application/json"}
        if os.environ.get("POWERCONTEXT_TOKEN"):
            headers["Authorization"] = "Bearer " + os.environ["POWERCONTEXT_TOKEN"]
        request = urllib.request.Request(base + endpoint, json.dumps(payload).encode(), headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        audit("powercontext", endpoint=endpoint, payload=payload, result=result, exit_code=0)
        return result

    def save(self, state):
        required = {"task_id", "task_description", "completed_steps", "pending_steps", "verification_results", "last_updated"}
        if not required.issubset(state):
            raise ValueError("Missing task state fields")
        return self.call("/v1/memory/remember", {"scope_id": os.environ["POWERCONTEXT_SCOPE"],
            "kind": "sdd-task-" + state["task_id"], "text": json.dumps(state, ensure_ascii=False)})

    def load(self, task):
        result = self.call("/v1/atomic-memory/list", {"scope_id": os.environ["POWERCONTEXT_SCOPE"],
            "kind": "sdd-task-" + task, "states": ["active"], "limit": 100})
        if result.get("next_cursor"):
            raise ValueError("Too many task snapshots: pagination needed")
        records = [json.loads(item["text"]) for item in result["items"]]
        if not records:
            raise ValueError("No saved task")
        return max(records, key=lambda s: s["last_updated"])

def context(task, resume=False):
    result = Store().context(task)
    if resume:
        state = PowerContext().load(task)
        result["restored_state"] = state
        result["next_action"] = state["pending_steps"][0] if state["pending_steps"] else "verify"
        result["generation_needed"] = "generate" in state["pending_steps"]
    audit("context", output=result, exit_code=0)
    return result

def generate(task):
    from .provider import request
    ctx = context(task)
    prompt = "Implement the specification using these actual sources. Return ONLY a JSON object with key source containing the full replacement sample_project/catalog.py. Do not modify tests.\n" + json.dumps(ctx)
    result = request([{"role":"user","content":prompt}])
    raw = result["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:-1])
    source = json.loads(raw)["source"]
    compile(source, "catalog.py", "exec")
    path = ROOT / "sample_project/catalog.py"
    before = path.read_text()
    path.write_text(source)
    import difflib
    diff = "".join(difflib.unified_diff(before.splitlines(True),source.splitlines(True),fromfile="before/catalog.py",tofile="after/catalog.py"))
    (ROOT / "evidence/applied.diff").write_text(diff)
    audit("minimax-applied", task_id=task, before_sha=digest(before), after_sha=digest(source), diff=diff, exit_code=0)
    return {"after_sha": digest(source)}

def verify(target):
    args = [sys.executable, "-m", "pytest", "-q", target]
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    return audit("pytest", business_sha=digest((ROOT/"sample_project/catalog.py").read_text()), invocation=args, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr,
        test_hashes={p.name:digest(p.read_text()) for p in sorted((ROOT/"tests").glob("test_*.py"))})
