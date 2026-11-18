#!/usr/bin/env bash
# Start the project's own PowerContext Server on 127.0.0.1:2893.
#
# Deliberately uses --no-env-file so no api.env / provider credential is ever
# discovered or loaded, and configures no model: the workbench only uses explicit
# Atomic Memory HTTP calls, which do not require a generation model.
#
# Usage: bash scripts/start_pc.sh [stop|status|log]
set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${YANXI_PC_VENV:-$HOME/.local/share/qoder-yanxi/pc-venv}"
PC="$VENV/bin/powercontext"
RUNTIME_DIR="$PROJECT_ROOT/.runtime/powercontext"
PID_FILE="$PROJECT_ROOT/.runtime/pc.pid"
LOG_FILE="$PROJECT_ROOT/.runtime/pc.log"

export POWERCONTEXT_HOME="${POWERCONTEXT_HOME:-$RUNTIME_DIR}"
export POWERCONTEXT_HTTP_HOST="${POWERCONTEXT_HTTP_HOST:-127.0.0.1}"
export POWERCONTEXT_HTTP_PORT="${POWERCONTEXT_HTTP_PORT:-2893}"
export POWERCONTEXT_ACCESS_MODE="${POWERCONTEXT_ACCESS_MODE:-disabled}"
export POWERCONTEXT_DATABASE_KIND="${POWERCONTEXT_DATABASE_KIND:-sqlite}"

BASE_URL="http://${POWERCONTEXT_HTTP_HOST}:${POWERCONTEXT_HTTP_PORT}"

is_running() {
  [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

case "${1:-start}" in
  stop)
    if is_running; then
      kill "$(cat "$PID_FILE")" && echo "stopped pid=$(cat "$PID_FILE")"
      rm -f "$PID_FILE"
    else
      echo "not running"
    fi
    exit 0
    ;;
  status)
    if is_running; then echo "running pid=$(cat "$PID_FILE")"; else echo "not running"; fi
    curl -s -m 4 "$BASE_URL/v1/server-info" || echo "(no server-info response)"
    exit 0
    ;;
  log)
    tail -n "${2:-40}" "$LOG_FILE"
    exit 0
    ;;
esac

[ -x "$PC" ] || { echo "Missing $PC - run bash scripts/setup_pc_env.sh" >&2; exit 127; }

if is_running; then
  echo "already running pid=$(cat "$PID_FILE")"
  exit 0
fi

mkdir -p "$POWERCONTEXT_HOME" "$(dirname "$PID_FILE")"
echo "starting PowerContext: home=$POWERCONTEXT_HOME url=$BASE_URL access=$POWERCONTEXT_ACCESS_MODE db=$POWERCONTEXT_DATABASE_KIND"
nohup "$PC" server run --host "$POWERCONTEXT_HTTP_HOST" --port "$POWERCONTEXT_HTTP_PORT" \
  --no-env-file --role "${POWERCONTEXT_ROLE:-all}" >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

for _ in $(seq 1 60); do
  if curl -sf -m 2 "$BASE_URL/v1/server-info" >/dev/null 2>&1; then
    echo "ready pid=$(cat "$PID_FILE")"
    curl -s "$BASE_URL/v1/server-info"
    exit 0
  fi
  if ! is_running; then
    echo "PROCESS EXITED - last log lines:" >&2
    tail -n 25 "$LOG_FILE" >&2
    exit 1
  fi
  sleep 1
done
echo "TIMEOUT waiting for $BASE_URL/v1/server-info" >&2
tail -n 25 "$LOG_FILE" >&2
exit 1
