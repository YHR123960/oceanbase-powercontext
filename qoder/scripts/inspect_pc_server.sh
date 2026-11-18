#!/usr/bin/env bash
# Dump the PowerContext server/config CLI help so the runbook matches the real binary.
set -u
VENV="${YANXI_PC_VENV:-$HOME/.local/share/qoder-yanxi/pc-venv}"
PC="$VENV/bin/powercontext"
echo "===== server --help ====="
"$PC" server --help 2>&1
echo
echo "===== config --help ====="
"$PC" config --help 2>&1
echo
echo "===== doctor --help ====="
"$PC" doctor --help 2>&1
