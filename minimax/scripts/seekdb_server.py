"""Isolated native seekdb service; foreground, Ctrl-C to stop."""
import time
import argparse
from pathlib import Path
import pylibseekdb
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument("--path",type=Path,default=root/".runtime/seekdb")
parser.add_argument("--port",type=int,default=2889)
args=parser.parse_args()
path=args.path.resolve()
path.mkdir(parents=True,exist_ok=True)
pylibseekdb.open_with_service(str(path),args.port)
print(f"seekdb ready on port {args.port}",flush=True)
while True: time.sleep(1)
