"""Clone committed sources, install two fresh venvs, initialize two fresh native databases."""
import argparse,json,os,signal,socket,subprocess,sys,time,uuid,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sdd.core import ROOT,audit
parser=argparse.ArgumentParser()
parser.add_argument("--uv",required=True,type=Path)
parser.add_argument("--python312",required=True,type=Path)
args=parser.parse_args()
run_id=uuid.uuid4().hex[:12]
base=ROOT/".runtime"/f"clean-{run_id}"
base.mkdir(parents=True)
checkout=base/"checkout"
uv=str(args.uv.resolve());python312=str(args.python312.resolve())
logfile=ROOT/"evidence"/f"reproduction-{run_id}.log"

def run(command,cwd=ROOT):
    p=subprocess.run(command,cwd=cwd,text=True,capture_output=True)
    with logfile.open("a") as f:f.write(json.dumps({"command":command,"cwd":str(cwd),"exit_code":p.returncode})+"\n"+p.stdout+p.stderr+"\n")
    audit("clean-command",invocation=command,exit_code=p.returncode,log=logfile.name)
    if p.returncode:raise RuntimeError("Reproduction command failed; see "+str(logfile))
    return p

run(["git","clone","--no-hardlinks","--local",str(ROOT.parent),str(checkout)])
project=checkout/"minimax"
venv=base/"app-venv";pcvenv=base/"pc-venv"
run([uv,"venv","--python",sys.executable,str(venv)])
run([uv,"pip","install","--python",str(venv/"bin/python"),"-r","requirements.lock"],project)
run([uv,"venv","--python",python312,str(pcvenv)])
run([uv,"pip","install","--python",str(pcvenv/"bin/python"),"-r","powercontext-requirements.lock"],project)
# Keep credentials out of all verification subprocesses: historical evidence suffices.
env={k:v for k,v in os.environ.items() if not k.startswith(("MINIMAX_","POWERCONTEXT_","SDD_"))}
attestation=base/"install-attestation.json"
attestation.write_text(json.dumps({"install_exit_code":0,"venv":str(venv),"fresh_seekdb":True,"checkout":str(checkout)}))
env.update({"SDD_DB_PORT":"2890","SDD_PC_EXECUTABLE":str(pcvenv/"bin/powercontext"),"SDD_CLEAN_ATTESTATION":str(attestation)})
initial=(project/"evidence/events.jsonl").read_bytes()
service_log=(ROOT/"evidence"/f"seekdb-clean-{run_id}.log").open("w")
invocation=[str(venv/"bin/python"),str(project/"scripts/seekdb_server.py"),"--port","2890","--path",str(base/"seekdb")]
service=subprocess.Popen(invocation,cwd=project,env=env,stdout=service_log,stderr=subprocess.STDOUT)
try:
    for _ in range(60):
        if service.poll() is not None:raise RuntimeError("fresh seekdb exited during startup")
        try:
            with socket.create_connection(("127.0.0.1",2890),timeout=1):break
        except OSError:time.sleep(.5)
    else:raise RuntimeError("fresh seekdb readiness timeout")
    audit("clean-seekdb-start",invocation=invocation,pid=service.pid,exit_code=0)
    result=subprocess.run([str(venv/"bin/python"),"scripts/acceptance.py"],cwd=project,env=env,text=True,capture_output=True)
    with logfile.open("a") as f:f.write(result.stdout+result.stderr)
    audit("clean-acceptance",invocation=[str(venv/"bin/python"),"scripts/acceptance.py"],exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)
    updated=(project/"evidence/events.jsonl").read_bytes()
    assert updated.startswith(initial)
    with (ROOT/"evidence/events.jsonl").open("ab") as f:f.write(updated[len(initial):])
    shutil.copy(project/"evidence/acceptance.json",ROOT/"evidence/acceptance.json")
    for log in (project/"evidence").glob("powercontext-*.log"):
        if not (ROOT/"evidence"/log.name).exists():shutil.copy(log,ROOT/"evidence"/log.name)
    summary={"source_commit":run(["git","rev-parse","HEAD"],checkout).stdout.strip(),"exit_code":result.returncode,"python":str(venv/"bin/python"),"log":logfile.name,"model_calls":0,"checks":json.loads((ROOT/"evidence/acceptance.json").read_text())}
    (ROOT/"evidence/reproduction.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
finally:
    service.send_signal(signal.SIGINT)
    try:service.wait(timeout=20)
    except subprocess.TimeoutExpired:service.terminate();service.wait(timeout=10)
    audit("clean-seekdb-exit",pid=service.pid,exit_code=service.returncode)
    service_log.close()
sys.exit(result.returncode)
