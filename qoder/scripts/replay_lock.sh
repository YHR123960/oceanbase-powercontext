#!/usr/bin/env bash
# Prove requirements.powercontext.lock replays in a clean venv from any checkout dir.
# Nothing here is reused from another project: the venv is throwaway and lives under .runtime/.
#
# Usage:
#   bash scripts/replay_lock.sh [--python /path/to/python3.12]
#   PYTHON_BIN=/path/to/python3.12 bash scripts/replay_lock.sh
#
# Capture the run as evidence:
#   bash scripts/replay_lock.sh > evidence/p1_lock_replay.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ "${1:-}" = "--python" ]; then
  PYTHON_BIN="${2:?--python 需要一个路径}"
fi

VENV="$ROOT/.runtime/replay-venv"
# Resolve the wheel first: an unquoted glob followed by [extras] would be read as a
# character class and match nothing.
WHEEL="$(ls "$ROOT"/vendor/powercontext-*.whl 2>/dev/null | head -1 || true)"
[ -n "$WHEEL" ] || { echo "缺少 $ROOT/vendor/powercontext-*.whl" >&2; exit 1; }

rm -rf "$VENV"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "找不到 $PYTHON_BIN" >&2; exit 127; }
"$PYTHON_BIN" -V
"$PYTHON_BIN" -m venv "$VENV"
set -x
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$ROOT/requirements.powercontext.lock"
"$VENV/bin/python" -m pip install --quiet "${WHEEL}[builtin,server,cli]"
set +x
"$VENV/bin/powercontext" --version
echo "replay OK: $(grep -vc '^#' "$ROOT/requirements.powercontext.lock") pinned dependencies + $(basename "$WHEEL")"
