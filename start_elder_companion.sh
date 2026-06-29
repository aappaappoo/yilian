#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT/.env"
  set +a
fi

if [ -z "${AMAP_API_KEY:-}" ] && [ -z "${SOUL_AMAP_API_KEY:-}" ] && [ -f "$ROOT/plugins/soul-companion/plugin.yaml" ]; then
  AMAP_API_KEY="$(
    python3 - "$ROOT/plugins/soul-companion/plugin.yaml" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(r"amap_api_key:\s*[\"']?([^\"'\s#]+)", text)
print(match.group(1).strip() if match else "")
PY
  )"
  export AMAP_API_KEY
fi

if [ -z "${AMAP_API_KEY:-}" ]; then
  echo "提示：没有找到 SOUL_AMAP_API_KEY/AMAP_API_KEY，天气/美食/住宿/景点查询会不可用；车票查询仍可用。" >&2
fi

export SOUL_HOME="${SOUL_HOME:-$ROOT/.soul_companion_home}"
export SOULBOT_ROOT="$ROOT"

mkdir -p "$SOUL_HOME/sessions" "$SOUL_HOME/logs" "$SOUL_HOME/memories"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
elif [ -x "$ROOT/venv/bin/python" ]; then
  PYTHON_BIN="$ROOT/venv/bin/python"
fi

cd "$ROOT"
exec "$PYTHON_BIN" "$ROOT/soul_cli.py" "$@"
