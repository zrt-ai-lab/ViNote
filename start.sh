#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
unset VIRTUAL_ENV

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

check_deps() {
    command -v python3 >/dev/null 2>&1 || err "需要 python3，请先安装"
    command -v ffmpeg  >/dev/null 2>&1 || err "需要 ffmpeg，请先安装: brew install ffmpeg"
    command -v node    >/dev/null 2>&1 || warn "未检测到 node，前端构建将跳过"

    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    log "Python $PYTHON_VERSION | ffmpeg $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"
}

setup_env() {
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            cp .env.example .env
            warn ".env 不存在，已从 .env.example 复制，请编辑填写 OPENAI_API_KEY"
        else
            err ".env 和 .env.example 均不存在"
        fi
    fi
    log ".env 已就绪"
}

install_backend() {
    if command -v uv >/dev/null 2>&1; then
        log "使用 uv 安装后端依赖..."
        uv sync --quiet || err "uv sync 失败"
    else
        log "使用 pip 安装后端依赖..."
        python3 -m pip install -e "." --quiet || err "pip install 失败"
    fi
    log "后端依赖安装完成"
}

build_frontend() {
    if ! command -v node >/dev/null 2>&1; then
        warn "跳过前端构建（未安装 node）"
        return
    fi

    if [ ! -d "web/node_modules" ]; then
        log "安装前端依赖..."
        (cd web && npm install --silent)
    fi

    if [ ! -f "static-build/index.html" ] || [ "web/src" -nt "static-build/index.html" ]; then
        log "构建前端..."
        (cd web && npm run build --silent)
        log "前端构建完成 → static-build/"
    else
        log "前端已是最新，跳过构建"
    fi
}

start_anp() {
    source .env 2>/dev/null || true

    if echo "${VIDEO_SEARCH_PROVIDERS:-local}" | grep -q "anp"; then
        if [ -d "backend/anp" ]; then
            if [ ! -f "backend/anp/did_keys/video_search/did.json" ]; then
                log "生成 ANP DID 密钥..."
                (cd backend/anp && python3 gen_did_keys.py)
            fi

            log "启动 DID 认证服务器..."
            (cd backend/anp && python3 client_did_server.py) &
            PIDS="$PIDS $!"
            sleep 2

            log "启动 ANP 搜索服务..."
            (cd backend/anp && python3 search_server_agent.py) &
            PIDS="$PIDS $!"
            sleep 2
        else
            warn "backend/anp 目录不存在，跳过 ANP 服务"
        fi
    fi
}

kill_port() {
    local port=$1
    local pids=""
    if command -v lsof >/dev/null 2>&1; then
        pids=$(lsof -ti:"$port" 2>/dev/null || true)
    elif command -v ss >/dev/null 2>&1; then
        pids=$(ss -tlnp "sport = :$port" 2>/dev/null | grep -oP 'pid=\K[0-9]+' || true)
    elif command -v netstat >/dev/null 2>&1; then
        pids=$(netstat -tlnp 2>/dev/null | grep ":$port " | awk '{print $NF}' | cut -d/ -f1 || true)
    fi
    if [ -n "$pids" ]; then
        warn "端口 $port 被占用（PID: $(echo $pids | tr '\n' ' ')），正在释放..."
        for p in $pids; do
            kill "$p" 2>/dev/null || true
        done
        sleep 1
        local remaining=""
        if command -v lsof >/dev/null 2>&1; then
            remaining=$(lsof -ti:"$port" 2>/dev/null || true)
        fi
        if [ -n "$remaining" ]; then
            for p in $remaining; do
                kill -9 "$p" 2>/dev/null || true
            done
            sleep 1
        fi
        log "端口 $port 已释放"
    fi
}

PIDS=""

cleanup() {
    echo ""
    log "停止所有服务..."
    for pid in $PIDS; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
    exit 0
}

main() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ViNote v1.3.0 启动"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    PIDS=""
    trap cleanup SIGTERM SIGINT EXIT

    check_deps
    setup_env
    install_backend
    build_frontend

    source .env 2>/dev/null || true
    HOST="${APP_HOST:-0.0.0.0}"
    PORT="${APP_PORT:-8999}"

    # 启动前检查并释放端口
    kill_port "$PORT"

    start_anp

    log "启动 ViNote → http://${HOST}:${PORT}"
    echo ""

    if command -v uv >/dev/null 2>&1; then
        uv run uvicorn backend.main:app --host "$HOST" --port "$PORT" --log-level warning &
    else
        python3 -m uvicorn backend.main:app --host "$HOST" --port "$PORT" --log-level warning &
    fi
    MAIN_PID=$!
    PIDS="$PIDS $MAIN_PID"

    wait "$MAIN_PID"
}

main "$@"
