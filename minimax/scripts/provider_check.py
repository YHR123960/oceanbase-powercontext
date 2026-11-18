import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from sdd.provider import load_env, request
load_env(sys.argv[1])
result=request([{"role":"user","content":"Reply only OK."}],limit=512)
print({"authenticated":True,"model":result.get("model"),"request_id":result.get("id"),"usage":result.get("usage"),"balance":"Generation succeeded; remaining/promotional balance not exposed by this endpoint"})
