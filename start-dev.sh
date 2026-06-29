#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

DISABLE_VRM_FROM_ARG=0

print_usage() {
  cat <<'EOF'
用法:
  ./start-dev.sh [选项]

选项:
  --no-vrm, --disable-vrm   禁用前端 3D VRM 人物模型，用静态 fallback 代替
  --with-vrm                强制启用前端 3D VRM 人物模型
  -h, --help                显示帮助

也可以用环境变量:
  VITE_DISABLE_VRM=1 ./start-dev.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-vrm|--disable-vrm)
      DISABLE_VRM_FROM_ARG=1
      shift
      ;;
    --with-vrm)
      DISABLE_VRM_FROM_ARG=0
      export VITE_DISABLE_VRM=0
      shift
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      echo "未知参数: $1"
      print_usage
      exit 1
      ;;
  esac
done

BACKEND_DIR="$ROOT_DIR/apps/backend"
LOG_DIR="$ROOT_DIR/log"
mkdir -p "$LOG_DIR"

ENV_FILE="${ENV_FILE:-}"
if [[ -z "$ENV_FILE" ]]; then
  if [[ -f "$ROOT_DIR/deploy/.env" ]]; then
    ENV_FILE="$ROOT_DIR/deploy/.env"
  else
    ENV_FILE="$ROOT_DIR/.env"
  fi
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "未找到环境变量文件: $ENV_FILE"
  echo "请先创建 .env 或 deploy/.env"
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

POSTGRES_USER="${POSTGRES_USER:-soulmeet}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-soulmeet_password}"
POSTGRES_DB="${POSTGRES_DB:-soulmeet_db}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

export CONTEXT_SQL_URL="${CONTEXT_SQL_URL:-postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_PORT}/${POSTGRES_DB}}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8080}"
export WEB_PORT="${WEB_PORT:-5173}"
export LOG_DIR="${LOG_DIR}"
export MEMORIES_DIR="${MEMORIES_DIR:-$ROOT_DIR/memories}"
export PYTHONPATH="$BACKEND_DIR${PYTHONPATH:+:$PYTHONPATH}"
export BACKEND_ORIGIN="${BACKEND_ORIGIN:-http://127.0.0.1:${PORT}}"
if [[ "$DISABLE_VRM_FROM_ARG" == "1" ]]; then
  export VITE_DISABLE_VRM=1
else
  export VITE_DISABLE_VRM="${VITE_DISABLE_VRM:-0}"
fi

PYTHON_BIN="${PYTHON_BIN:-}"

python_has_backend_deps() {
  local candidate="$1"
  "$candidate" - <<'PY' >/dev/null 2>&1
import aiohttp
import fastapi
import uvicorn
PY
}

if [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_CANDIDATES=()
  [[ -x "$ROOT_DIR/.venv/bin/python" ]] && PYTHON_CANDIDATES+=("$ROOT_DIR/.venv/bin/python")
  [[ -x "$ROOT_DIR/.venv-test/bin/python" ]] && PYTHON_CANDIDATES+=("$ROOT_DIR/.venv-test/bin/python")
  [[ -n "${CONDA_PREFIX:-}" && -x "$CONDA_PREFIX/bin/python" ]] && PYTHON_CANDIDATES+=("$CONDA_PREFIX/bin/python")
  [[ -x "$HOME/miniforge3/envs/soulbot/bin/python" ]] && PYTHON_CANDIDATES+=("$HOME/miniforge3/envs/soulbot/bin/python")
  [[ -x "$HOME/miniconda3/envs/soulbot/bin/python" ]] && PYTHON_CANDIDATES+=("$HOME/miniconda3/envs/soulbot/bin/python")
  command -v python3 >/dev/null 2>&1 && PYTHON_CANDIDATES+=("$(command -v python3)")
  command -v python >/dev/null 2>&1 && PYTHON_CANDIDATES+=("$(command -v python)")
  [[ -x "/usr/bin/python3" ]] && PYTHON_CANDIDATES+=("/usr/bin/python3")

  for candidate in "${PYTHON_CANDIDATES[@]}"; do
    if "$candidate" --version >/dev/null 2>&1 && python_has_backend_deps "$candidate"; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

PNPM_BIN="${PNPM_BIN:-pnpm}"

BACKEND_LOG="$LOG_DIR/backend.log"
WEB_LOG="$LOG_DIR/web.log"
DB_LOG="$LOG_DIR/db.log"
PID_FILE="$LOG_DIR/dev.pids"

PIDS=()

stop_pid() {
  local pid="$1"
  local label="${2:-process}"
  if [[ -z "$pid" || ! "$pid" =~ ^[0-9]+$ ]]; then
    return
  fi
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "停止旧 ${label}: pid=${pid}"
    kill "$pid" >/dev/null 2>&1 || true
  fi
}

stop_stale_processes() {
  if [[ -f "$PID_FILE" ]]; then
    while IFS=: read -r name pid; do
      stop_pid "$pid" "${name:-dev-process}"
    done <"$PID_FILE"
  fi

  if command -v lsof >/dev/null 2>&1; then
    while read -r pid; do
      stop_pid "$pid" "backend-port-${PORT}"
    done < <(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
    while read -r pid; do
      stop_pid "$pid" "web-port-${WEB_PORT}"
    done < <(lsof -tiTCP:"$WEB_PORT" -sTCP:LISTEN 2>/dev/null || true)
  fi

  sleep 1
}

postgres_port_open() {
  nc -z 127.0.0.1 "$POSTGRES_PORT" >/dev/null 2>&1 && return 0
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$POSTGRES_PORT" -sTCP:LISTEN >/dev/null 2>&1 && return 0
  fi
  return 1
}

stop_processes() {
  if [[ ${#PIDS[@]} -gt 0 ]]; then
    echo ""
    echo "正在停止本地开发进程..."
    for pid in "${PIDS[@]}"; do
      if kill -0 "$pid" >/dev/null 2>&1; then
        kill "$pid" >/dev/null 2>&1 || true
      fi
    done
  fi
  rm -f "$PID_FILE"
}

trap stop_processes EXIT INT TERM

start_db() {
  if ! command -v docker >/dev/null 2>&1; then
    if postgres_port_open; then
      echo "未找到 docker，检测到 PostgreSQL 已在 ${POSTGRES_PORT} 端口运行，跳过数据库容器启动。"
      return
    fi
    echo "未找到 docker，且 ${POSTGRES_PORT} 端口没有可用 PostgreSQL。"
    exit 1
  fi

  echo "启动 PostgreSQL 容器..."
  if {
    docker compose --env-file "$ENV_FILE" -f "$ROOT_DIR/deploy/docker-compose.dev.yml" up -d db
  } >>"$DB_LOG" 2>&1; then
    return
  fi

  if postgres_port_open; then
    echo "Docker 数据库容器启动失败，但检测到 PostgreSQL 已在 ${POSTGRES_PORT} 端口运行，继续使用本机数据库。"
    echo "Docker 失败详情见: $DB_LOG"
    return
  fi

  echo "Docker 数据库容器启动失败，且 ${POSTGRES_PORT} 端口没有可用 PostgreSQL。"
  echo "最近的数据库启动日志:"
  tail -n 40 "$DB_LOG" || true
  exit 1
}

start_process() {
  local name="$1"
  local logfile="$2"
  shift 2

  echo "启动 ${name}，日志: ${logfile}"
  "$@" >>"$logfile" 2>&1 &
  local pid=$!
  PIDS+=("$pid")
  echo "${name}:${pid}" >>"$PID_FILE"
}

check_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "缺少命令: $command_name"
    exit 1
  fi
}

check_command "$PNPM_BIN"
if [[ ! -x "$PYTHON_BIN" ]] && ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "缺少可用 Python: $PYTHON_BIN"
  exit 1
fi
if ! "$PYTHON_BIN" --version >/dev/null 2>&1; then
  echo "Python 无法运行: $PYTHON_BIN"
  exit 1
fi
if ! python_has_backend_deps "$PYTHON_BIN"; then
  echo "Python 缺少后端运行依赖: $PYTHON_BIN"
  echo "请安装 apps/backend/requirements.txt，或设置 PYTHON_BIN 指向可运行后端的环境。"
  exit 1
fi

stop_stale_processes
: >"$PID_FILE"

start_db

start_process "backend" "$BACKEND_LOG" "$PYTHON_BIN" "$BACKEND_DIR/main.py"
start_process "web" "$WEB_LOG" "$PNPM_BIN" dev:web

cat <<EOF

Soulmeet 本地开发环境已启动

前端: https://localhost:5173 或 http://localhost:5173
后端: https://localhost:${PORT} 或 http://localhost:${PORT}
前端代理后端: ${BACKEND_ORIGIN}
3D 人物模型: $([[ "$VITE_DISABLE_VRM" == "1" ]] && echo "已禁用（fallback 模式）" || echo "已启用")

日志:
  backend     $BACKEND_LOG
  web         $WEB_LOG
  db          $DB_LOG

PID 文件: $PID_FILE

按 Ctrl+C 停止本次启动的本地进程。数据库容器不会自动停止。
EOF

wait
