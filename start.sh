#!/usr/bin/env bash
# WeSmartFlow 一键启动脚本
# 用法：./start.sh
# 说明：使用 edu-agent conda 环境，先杀掉旧的前后端进程，再分别启动后端(8080)与前端(5173)。
# 默认按生产安全模式运行，后端不会因源码变更重启并中断长生成。

set -euo pipefail

CONDA_ENV="edu-agent"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/.runtime"
BACKEND_PORT="8080"
FRONTEND_PORT="5173"

mkdir -p "$LOG_DIR"

log() { printf '\033[1;34m[启动]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[警告]\033[0m %s\n' "$*"; }

kill_port() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    log "检测到端口 $port 被占用，正在结束进程：$pids"
    # 逐行处理，避免 pids 中带空格导致 kill 报错
    printf '%s\n' "$pids" | xargs -r kill 2>/dev/null || true
  fi
}

# 1. 结束旧进程
log "清理旧的 edu-agent 前后端进程..."
kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"
pkill -f "$BACKEND_DIR/main.py" 2>/dev/null || true
pkill -f "$FRONTEND_DIR" 2>/dev/null || true
sleep 1

# 2. 加载 conda 环境（python / npm 均来自 edu-agent）
log "激活 conda 环境：$CONDA_ENV"
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"

# 3. 安装前端依赖（首次运行需要，之后自动跳过）
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  log "首次运行，安装前端依赖（npm install）..."
  (cd "$FRONTEND_DIR" && npm install)
fi

# 3.1 安装各探索示例 Demo 的依赖（前端 predev 会逐个构建这些示例，需要各自 node_modules）
for pkg in "$ROOT_DIR"/examples/*/package.json; do
  [ -e "$pkg" ] || continue
  demo_dir="$(dirname "$pkg")"
  if [ ! -d "$demo_dir/node_modules" ]; then
    log "安装示例依赖：$(basename "$demo_dir")"
    (cd "$demo_dir" && npm install)
  fi
done

# 4. 启动后端（从 backend 目录运行，读取仓库根目录 .env，端口 8080）
log "启动后端服务..."
(
  cd "$BACKEND_DIR"
  WESMARTFLOW_RELOAD="${WESMARTFLOW_RELOAD:-false}" \
    nohup python main.py >"$LOG_DIR/backend.log" 2>&1 &
  echo $! >"$LOG_DIR/backend.pid"
)

# 5. 启动前端（Vite 开发服务器，端口 5173，/api 代理到后端 8080）
log "启动前端服务..."
(
  cd "$FRONTEND_DIR"
  nohup npm run dev >"$LOG_DIR/frontend.log" 2>&1 &
  echo $! >"$LOG_DIR/frontend.pid"
)

# 6. 健康检查（首次会构建全部示例，给足等待时间）
wait_url() {
  local url="$1" attempts="$2" name="$3"
  local i=0
  while [ "$i" -lt "$attempts" ]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "$name 已就绪：$url"
      return 0
    fi
    sleep 2
    i=$((i + 1))
  done
  warn "$name 未在预期时间内响应，请查看日志：$LOG_DIR"
  return 1
}

wait_url "http://localhost:$BACKEND_PORT/health" 15 "后端"
wait_url "http://localhost:$FRONTEND_PORT" 30 "前端"

log "完成。前端地址 http://localhost:$FRONTEND_PORT ，日志目录 $LOG_DIR"
