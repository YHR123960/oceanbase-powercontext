"""Actual acceptance: fresh DB and PC home; replay genuine provider evidence, no API call."""
import json,os,subprocess,sys,uuid,time,signal,shutil,tempfile,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sdd.core import ROOT, Store, PowerContext, audit, digest, verify
os.environ.setdefault("SDD_DATABASE","minimax_sdd_accept_"+uuid.uuid4().hex[:12])
os.environ.setdefault("SDD_DB_PORT","2889")
report={str(i):{"status":"FAIL","detail":"not verified"} for i in range(1,7)}
run_id=uuid.uuid4().hex[:12]
runroot=ROOT/".runtime"/run_id
runroot.mkdir(parents=True)

def cli(*args):
    env={**os.environ,"PYTHONPATH":str(ROOT/"src")}
    invocation=[sys.executable,"-m","sdd",*args]
    p=subprocess.run(invocation,cwd=ROOT,env=env,text=True,capture_output=True)
    audit("subprocess",pid=p.pid if hasattr(p,"pid") else None,invocation=invocation,stdout=p.stdout,stderr=p.stderr,exit_code=p.returncode)
    if p.returncode: raise RuntimeError(p.stderr)
    return json.loads(p.stdout)

def passed(i,detail):report[str(i)]={"status":"PASS","detail":detail}
def failed(i,exc):report[str(i)]={"status":"FAIL","detail":str(exc)[:500]}

spec=ROOT/"specs/status.md"
original=spec.read_text()
try:
    store=Store()
    for path,kind in [("sample_project/catalog.py","code"),("tests/test_target.py","target"),("tests/test_regression.py","regression")]:store.ingest(path,kind,"status-filter")
    outputs=[]
    for version in ("v1","v2"):
        spec.write_text((ROOT/f"specs/status_{version}.fixture").read_text())
        store.ingest("specs/status.md","spec","status-filter")
        outputs.append(cli("context"))
    s1,s2=[next(s for s in out["sources"] if s["kind"]=="spec") for out in outputs]
    assert s1["sha"]!=s2["sha"] and "V2" in s2["content"] and "V1" not in s2["content"]
    assert all((ROOT/s["path"]).is_file() for s in outputs[-1]["sources"])
    rows=store.sql("SELECT sha,active FROM documents WHERE path=%s",("specs/status.md",),True)
    assert sum(bool(r["active"]) for r in rows)==1 and len(rows)==2
    passed(3,"four source types, live V1/V2 replacement, old version inactive")
    passed(4,"native seekdb SQL persisted and used by fresh context processes")
except Exception as e:failed(3,e);failed(4,e)
finally:
    spec.write_text(original)
    if "store" in globals():store.ingest("specs/status.md","spec","status-filter")
try:
    events=[json.loads(line) for line in (ROOT/"evidence/events.jsonl").read_text().splitlines()]
    applied=[e for e in events if e["event"]=="minimax-applied"][-1]
    calls=[e for e in events if e["event"]=="minimax-response" and "request" in e and "full replacement" in e["request"]["messages"][0]["content"]]
    call=calls[-1]
    raw=call["response"]["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"):raw="\n".join(raw.splitlines()[1:-1])
    source=json.loads(raw)["source"]
    assert call["response"]["id"] and digest(source)==applied["after_sha"]==digest((ROOT/"sample_project/catalog.py").read_text())
    assert applied["before_sha"]==digest((ROOT/"evidence/before_catalog.py.txt").read_text())
    promptctx=json.loads(call["request"]["messages"][0]["content"].split("\n",1)[1])
    assert {x["kind"] for x in promptctx["sources"]}=={"spec","code","target","regression"}
    assert all(digest(x["content"])==x["sha"] for x in promptctx["sources"])
    assert next(x["sha"] for x in promptctx["sources"] if x["kind"]=="code")==applied["before_sha"]
    passed(2,"provider request/response ID, actual DB context, response source and applied source hashes agree")
    before=[e for e in events if e["event"]=="pytest" and e["exit_code"]==1 and "6 failed" in e["stdout"]][0]
    after=verify("tests/test_target.py");regression=verify("tests/test_regression.py")
    assert after["exit_code"]==regression["exit_code"]==0
    for name in ("test_target.py","test_regression.py"):
        assert before["test_hashes"][name]==after["test_hashes"][name]
    # Reproduce the red baseline using the same untouched tests in an isolated copy.
    baseline=runroot/"baseline"
    shutil.copytree(ROOT/"sample_project",baseline/"sample_project",ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT/"tests",baseline/"tests",ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT/"pytest.ini",baseline/"pytest.ini")
    (baseline/"sample_project/catalog.py").write_text((ROOT/"evidence/before_catalog.py.txt").read_text())
    red=subprocess.run([sys.executable,"-m","pytest","-q","tests/test_target.py"],cwd=baseline,text=True,capture_output=True)
    audit("baseline-replay",invocation=[sys.executable,"-m","pytest","-q","tests/test_target.py"],business_sha=applied["before_sha"],exit_code=red.returncode,stdout=red.stdout,stderr=red.stderr)
    assert red.returncode==1 and "6 failed" in red.stdout and "AssertionError" in red.stdout and "ImportError" not in red.stdout
    passed(6,"same frozen targets: six real behavior failures replayed, six pass after; three regression tests pass")
except Exception as e:failed(6,e)

pc=None;log=None
try:
    from datetime import datetime,timezone
    # Own this exact service process and brand-new home; no shared PowerContext state.
    pc_executable=os.environ.get("SDD_PC_EXECUTABLE",str(ROOT/".runtime/pc-venv/bin/powercontext"))
    pcenv={k:v for k,v in os.environ.items() if not k.startswith(("POWERCONTEXT_","MINIMAX_"))}
    pcenv.update({"POWERCONTEXT_HOME":str(runroot/"powercontext"),"POWERCONTEXT_SERVER_HTTP_PORT":"2891","POWERCONTEXT_SERVER_HTTP_HOST":"127.0.0.1","POWERCONTEXT_SERVER_ACCESS_MODE":"disabled","POWERCONTEXT_SERVER_DATABASE_KIND":"sqlite"})
    os.environ["POWERCONTEXT_URL"]="http://127.0.0.1:2891"
    log=(ROOT/"evidence"/f"powercontext-{run_id}.log").open("w")
    def start():
        proc=subprocess.Popen([pc_executable,"server","run","--no-env-file"],cwd=ROOT,env=pcenv,stdout=log,stderr=subprocess.STDOUT)
        for _ in range(60):
            if proc.poll() is not None:raise RuntimeError("PowerContext startup failed; see service log")
            try:
                with urllib.request.urlopen(os.environ["POWERCONTEXT_URL"]+"/health/ready",timeout=1) as response:
                    if response.status==200:
                        audit("powercontext-start",pid=proc.pid,home=str(runroot/"powercontext"),invocation=[pc_executable,"server","run","--no-env-file"],exit_code=0)
                        return proc
            except Exception:time.sleep(.5)
        proc.terminate();proc.wait(timeout=15);raise RuntimeError("PowerContext readiness timeout")
    pc=start()
    scope=PowerContext().call("/v1/scopes",{"title":"MiniMax SDD acceptance","summary":"Isolated state persistence proof","idempotency_key":run_id})
    os.environ["POWERCONTEXT_SCOPE"]=scope["scope_id"]
    empty=PowerContext().call("/v1/atomic-memory/list",{"scope_id":scope["scope_id"],"kind":"sdd-task-status-filter","states":["active"]})
    assert empty["items"]==[]
    state={"task_id":"status-filter","task_description":"Add status filtering while preserving pagination", "completed_steps":["ingest","generate","target-tests","regression-tests"],"pending_steps":["package-evidence"],"verification_results":{"target":6,"regression":3,"passed":True},"last_updated":datetime.now(timezone.utc).isoformat()}
    statefile=runroot/"state-input.json";statefile.write_text(json.dumps(state))
    cli("state-save","--path",str(statefile))
    pc.send_signal(signal.SIGINT);pc.wait(timeout=30)
    audit("powercontext-exit",pid=pc.pid,exit_code=pc.returncode)
    pc=start() # stronger than required: service and CLI both restarted
    restored=cli("context","--resume")
    assert restored["restored_state"]==state and restored["next_action"]=="package-evidence" and restored["generation_needed"] is False
    audit("resume-decision",next_action=restored["next_action"],generation_needed=restored["generation_needed"],completed_steps=state["completed_steps"],exit_code=0)
    passed(5,"empty scope -> real PowerContext Memory -> clean service exit/restart -> fresh CLI reads state and skips completed generation")
except Exception as e:failed(5,e)
finally:
    if pc and pc.poll() is None:pc.send_signal(signal.SIGINT);pc.wait(timeout=30)
    if log:log.close()
# Clean installation attestation is created only by scripts/reproduce.py after new env and fresh seekdb.
attestation=os.environ.get("SDD_CLEAN_ATTESTATION")
if attestation:
    data=json.loads(Path(attestation).read_text())
    if data.get("install_exit_code")==0 and data.get("fresh_seekdb") and Path(sys.prefix).resolve()==Path(data["venv"]).resolve():passed(1,"fresh checkout copy, newly installed venv/dependencies, fresh seekdb and fresh PowerContext home")
exit_code=0 if all(x["status"]=="PASS" for x in report.values()) else 1
audit("acceptance",report=report,run_id=run_id,exit_code=exit_code)
(ROOT/"evidence/acceptance.json").write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2));sys.exit(exit_code)
