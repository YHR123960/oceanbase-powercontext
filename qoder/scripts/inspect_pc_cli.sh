#!/usr/bin/env bash
# Inspect the PowerContext CLI surface that this project depends on.
# Usage: bash scripts/inspect_pc_cli.sh
set -u
VENV="${YANXI_PC_VENV:-$HOME/.local/share/qoder-yanxi/pc-venv}"
PC="$VENV/bin/powercontext"

echo "venv=$VENV"
if [ ! -x "$PC" ]; then
  echo "POWERCONTEXT_BINARY_MISSING=$PC"
  exit 127
fi
echo "--- version ---"
"$VENV/bin/python" -m pip show powercontext 2>/dev/null | sed -n '1,4p'
echo "--- commands ---"
"$PC" --help 2>&1 | sed -n '/Commands/,$p'
echo "--- server help ---"
"$PC" server --help 2>&1
