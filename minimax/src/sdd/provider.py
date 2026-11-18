"""Bounded MiniMax request with explicit credential file and safe audit."""
import json
import os
import shlex
import urllib.request
import urllib.error
from pathlib import Path

ALLOWED = {"MINIMAX_API_KEY", "MINIMAX_ENDPOINT", "MINIMAX_MODEL"}

def load_env(path):
    path=Path(path).expanduser()
    if path.stat().st_mode & 0o077:
        raise ValueError("Credential file must have mode 600")
    for line in path.read_text().splitlines():
        parts=shlex.split(line,comments=True)
        if parts and parts[0]=="export": parts=parts[1:]
        if not parts: continue
        if len(parts)!=1 or "=" not in parts[0]: raise ValueError("Invalid env assignment")
        key,value=parts[0].split("=",1)
        if key in ALLOWED: os.environ[key]=value
    if not os.environ.get("MINIMAX_API_KEY"): raise ValueError("MINIMAX_API_KEY is missing")

def request(messages,limit=4096):
    endpoint=os.environ.get("MINIMAX_ENDPOINT","https://api.minimax.cn/v1/chat/completions")
    from urllib.parse import urlsplit
    parsed=urlsplit(endpoint)
    if parsed.scheme!="https" or parsed.hostname not in {"api.minimax.cn","api.minimaxi.com","api.minimax.io"} or parsed.username or parsed.password:
        raise ValueError("Only official HTTPS MiniMax API hosts are allowed")
    model=os.environ.get("MINIMAX_MODEL","MiniMax-M3.1-Flash")
    payload={"model":model,"messages":messages,"max_completion_tokens":limit,"reasoning_effort":"low"}
    req=urllib.request.Request(endpoint,json.dumps(payload).encode(),{"Content-Type":"application/json","Authorization":"Bearer "+os.environ["MINIMAX_API_KEY"]})
    try:
        with urllib.request.urlopen(req,timeout=120) as resp: result=json.load(resp)
    except urllib.error.HTTPError as exc:
        # Never include raw body, headers or credentials in exception output.
        raise ValueError("MiniMax HTTP status "+str(exc.code)) from None
    for choice in result.get("choices",[]): choice.get("message",{}).pop("reasoning_content",None)
    from .core import audit
    audit("minimax-response",task_id="status-filter",model=model,endpoint=endpoint,request=payload,response=result,exit_code=0)
    if result.get("base_resp",{}).get("status_code",0)!=0: raise ValueError("MiniMax provider status "+str(result["base_resp"]["status_code"]))
    if not result.get("choices"): raise ValueError("MiniMax returned no choices")
    if result["choices"][0].get("finish_reason")!="stop": raise ValueError("MiniMax output incomplete; no automatic retry")
    return result
