#!/usr/bin/env bash
# Thin wrapper so docs and scripts can call the project's own PowerContext build.
#   bash scripts/pc.sh <powercontext args...>
# Overrides: YANXI_PC_VENV (venv root), YANXI_PC_BIN (explicit executable).
set -u
VENV="${YANXI_PC_VENV:-$HOME/.local/share/qoder-yanxi/pc-venv}"
PC="${YANXI_PC_BIN:-$VENV/bin/powercontext}"
if [ ! -x "$PC" ]; then
  echo "PowerContext executable not found: $PC" >&2
  echo "Run: bash scripts/setup_pc_env.sh" >&2
  exit 127
fi
exec "$PC" "$@"
