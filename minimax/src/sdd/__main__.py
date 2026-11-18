import argparse
import json
import sys
from pathlib import Path
from .core import Store, PowerContext, context, generate, verify, audit

def main():
    parser=argparse.ArgumentParser(description="MiniMax SDD context workflow")
    parser.add_argument("command",choices=["init","ingest","context","state-save","state-load","generate","verify"])
    parser.add_argument("--task",default="status-filter")
    parser.add_argument("--path")
    parser.add_argument("--kind",choices=["spec","code","target","regression"])
    parser.add_argument("--resume",action="store_true")
    parser.add_argument("--env-file",help="Explicit private MiniMax env file, never logged")
    args=parser.parse_args()
    try:
        if args.env_file:
            from .provider import load_env
            load_env(args.env_file)
        if args.command=="init": Store(); result={"initialized":True}
        elif args.command=="ingest": result=Store().ingest(args.path,args.kind,args.task)
        elif args.command=="context": result=context(args.task,args.resume)
        elif args.command=="state-save": result=PowerContext().save(json.loads(Path(args.path).read_text()))
        elif args.command=="state-load": result=PowerContext().load(args.task)
        elif args.command=="generate": result=generate(args.task)
        else:
            result=verify(args.path or "tests")
            print(json.dumps(result,ensure_ascii=False)); return result["exit_code"]
        print(json.dumps(result,ensure_ascii=False)); return 0
    except Exception as exc:
        # Provider exceptions can contain secrets; only expose type and configuration keys.
        message=str(exc) if isinstance(exc,(KeyError,ValueError,FileNotFoundError)) else type(exc).__name__
        print(json.dumps({"error":message}),file=sys.stderr)
        audit("error",error=message,exit_code=1); return 1

if __name__=="__main__": sys.exit(main())
