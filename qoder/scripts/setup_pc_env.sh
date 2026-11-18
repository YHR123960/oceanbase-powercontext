#!/usr/bin/env bash
# Build 研习工作台's own PowerContext environment from the vendored official wheel.
#
# The script never reuses another project's venv: it creates a fresh venv, installs
# vendor/powercontext-*.whl with the server extras, and writes a dependency lock that a
# reviewer can replay from any checkout directory.
#
# Prerequisite: a CPython >= 3.11 and < 4.0. Point at your own with --python or PYTHON_BIN.
#
# Usage:
#   bash scripts/setup_pc_env.sh [--python /path/to/python3.12] [--venv /path/to/venv]
#   PYTHON_BIN=/path/to/python3.12 bash scripts/setup_pc_env.sh
#
# Replay an existing lock instead:
#   python3.12 -m venv ~/.local/share/qoder-yanxi/pc-venv
#   ~/.local/share/qoder-yanxi/pc-venv/bin/python -m pip install -r requirements.powercontext.lock
#   ~/.local/share/qoder-yanxi/pc-venv/bin/python -m pip install ./vendor/powercontext-*.whl[builtin,server,cli]
set -euo pipefail

usage() {
  sed -n '/^set -euo/q; s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"
}

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"
VENV_DIR="${YANXI_PC_VENV:-$HOME/.local/share/qoder-yanxi/pc-venv}"
LOCK_FILE="$PROJECT_ROOT/requirements.powercontext.lock"

while [ $# -gt 0 ]; do
  case "$1" in
    --python) PYTHON_BIN="${2:-}"; [ -n "$PYTHON_BIN" ] || { echo "--python 需要一个路径" >&2; exit 2; }; shift 2 ;;
    --python=*) PYTHON_BIN="${1#*=}"; shift ;;
    --venv) VENV_DIR="${2:-}"; [ -n "$VENV_DIR" ] || { echo "--venv 需要一个路径" >&2; exit 2; }; shift 2 ;;
    --venv=*) VENV_DIR="${1#*=}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数：$1" >&2; usage >&2; exit 2 ;;
  esac
done

python_usable() {
  "$1" -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info < (4, 0) else 1)' 2>/dev/null
}

find_python() {
  if [ -n "$PYTHON_BIN" ]; then
    command -v "$PYTHON_BIN" >/dev/null 2>&1 || [ -x "$PYTHON_BIN" ] \
      || { echo "找不到解释器：$PYTHON_BIN" >&2; exit 127; }
    python_usable "$PYTHON_BIN" \
      || { echo "$PYTHON_BIN 不是 CPython >=3.11,<4.0：$("$PYTHON_BIN" -V 2>&1)" >&2; exit 1; }
    return
  fi
  for candidate in python3.13 python3.12 python3.11 python3 /usr/local/bin/python3 /usr/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1 && python_usable "$candidate"; then
      PYTHON_BIN="$(command -v "$candidate")"
      return
    fi
  done
  echo "未找到 CPython >=3.11 且 <4.0 的解释器。请安装一个，或用 --python /path/to/python3.12 指定。" >&2
  echo "（本脚本不下载 Python，也不依赖任何其他项目的 .runtime。）" >&2
  exit 127
}

WHEEL="$(ls "$PROJECT_ROOT"/vendor/powercontext-*.whl 2>/dev/null | head -1 || true)"
[ -n "$WHEEL" ] || { echo "缺少 $PROJECT_ROOT/vendor/powercontext-*.whl" >&2; exit 1; }
find_python

echo "== interpreter =="
"$PYTHON_BIN" -V
echo "== venv: $VENV_DIR =="
[ -x "$VENV_DIR/bin/python" ] || "$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip

echo "== install $(basename "$WHEEL")[builtin,server,cli] =="
"$VENV_DIR/bin/python" -m pip install "$WHEEL[builtin,server,cli]"

echo "== lock dependencies =="
# pip freeze would embed this machine's absolute wheel path, which cannot be replayed
# elsewhere; powercontext itself therefore stays out of the lock and comes from vendor/.
{
  echo "# 由 scripts/setup_pc_env.sh 生成：PowerContext 官方 wheel 的全部依赖，版本精确锁定。"
  echo "# powercontext 本体不在此文件中：从 vendor/ 安装，避免写入开发机绝对路径。"
  echo "#   python -m pip install -r requirements.powercontext.lock"
  echo "#   python -m pip install ./vendor/powercontext-*.whl[builtin,server,cli]"
  "$VENV_DIR/bin/python" -m pip freeze | grep -v '^powercontext @ '
} > "$LOCK_FILE"
echo "lock entries: $(grep -vc '^#' "$LOCK_FILE") -> $LOCK_FILE"

echo "== verify =="
"$VENV_DIR/bin/python" -m pip show powercontext | sed -n '1,4p'
"$VENV_DIR/bin/powercontext" --version
sha256sum "$WHEEL"
