#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
unset VIRTUAL_ENV

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

VERSION="$(tr -d '[:space:]' < VERSION 2>/dev/null || true)"
VERSION="${VERSION:-1.4.0}"

PIDS=()

log() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err() {
    echo -e "${RED}[✗]${NC} $1" >&2
    exit 1
}

cleanup() {
    local status="$1"
    trap - EXIT INT TERM

    if [ "${#PIDS[@]}" -gt 0 ]; then
        echo ""
        log "停止已启动的 ViNote 子进程..."
        for pid in "${PIDS[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null || true
            fi
        done
        wait 2>/dev/null || true
    fi

    exit ${status}
}

trap 'cleanup $?' EXIT
trap 'cleanup 130' INT
trap 'cleanup 143' TERM

read_env_value() {
    local key="$1"
    local default_value="${2:-}"
    local line

    if [ ! -f .env ]; then
        printf '%s\n' "$default_value"
        return
    fi

    line="$(grep -E "^[[:space:]]*${key}=" .env 2>/dev/null | tail -n 1 || true)"
    if [ -z "$line" ]; then
        printf '%s\n' "$default_value"
        return
    fi

    line="${line#*=}"
    line="${line%%$'\r'}"
    line="${line%\"}"
    line="${line#\"}"
    line="${line%\'}"
    line="${line#\'}"
    printf '%s\n' "$line"
}

check_python_version() {
    command -v python3 >/dev/null 2>&1 || err "需要 Python 3.10+，请先安装 python3"
    python3 - <<'PY' || err "Python 版本过低，需要 3.10+"
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

check_node_version() {
    command -v node >/dev/null 2>&1 || err "需要 Node.js 20.19+ 或 22.12+，请先安装 Node.js"
    command -v npm >/dev/null 2>&1 || err "需要 npm，请确认 Node.js 安装完整"

    local node_version
    node_version="$(node -p 'process.versions.node')"
    NODE_VERSION="$node_version" python3 - <<'PY' || err "Node.js ${node_version} 不满足要求，需要 20.19+ 或 22.12+"
import os
major, minor, *_ = [int(part) for part in os.environ["NODE_VERSION"].split(".")]
ok = (major == 20 and minor >= 19) or (major == 22 and minor >= 12) or major > 22
raise SystemExit(0 if ok else 1)
PY
}

check_deps() {
    check_python_version
    command -v uv >/dev/null 2>&1 || err "需要 uv，请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh"
    command -v ffmpeg >/dev/null 2>&1 || err "需要 FFmpeg，请先安装: brew install ffmpeg"
    check_node_version

    local python_version
    local ffmpeg_version
    local node_version
    python_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    ffmpeg_version="$(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"
    node_version="$(node -p 'process.versions.node')"
    log "Python ${python_version} | Node ${node_version} | ffmpeg ${ffmpeg_version}"
}

setup_env() {
    if [ ! -f .env ]; then
        [ -f .env.example ] || err ".env 和 .env.example 均不存在"
        cp .env.example .env
        warn ".env 不存在，已从 .env.example 复制。请编辑 .env 后重新运行 ./start.sh"
        warn "基础界面可在 OPENAI_API_KEY 为空时启动，但 AI 生成能力不可用"
        exit 2
    fi
    log ".env 已就绪"
}

validate_config() {
    APP_HOST="$(read_env_value APP_HOST "127.0.0.1")"
    APP_PORT="$(read_env_value APP_PORT "8999")"
    OPENAI_API_KEY_VALUE="$(read_env_value OPENAI_API_KEY "")"

    if ! [[ "$APP_PORT" =~ ^[0-9]+$ ]] || [ "$APP_PORT" -lt 1 ] || [ "$APP_PORT" -gt 65535 ]; then
        err "APP_PORT 必须是 1-65535 的数字"
    fi

    if [ -z "$OPENAI_API_KEY_VALUE" ]; then
        warn "OPENAI_API_KEY 为空，AI 总结、问答和翻译功能不可用"
    fi
}

install_backend() {
    log "使用 uv 安装后端依赖..."
    local asr_provider
    local extras=()
    asr_provider="$(read_env_value ASR_PROVIDER "whisper")"
    case "$asr_provider" in
        whisper) ;;
        funasr|qwen3) extras+=(--extra "$asr_provider") ;;
        *) err "ASR_PROVIDER 必须为 whisper、funasr 或 qwen3" ;;
    esac
    uv sync --frozen "${extras[@]}" || err "uv sync --frozen 失败"
    # 后续 uv run 保留刚刚按配置安装的可选依赖。
    export UV_NO_SYNC=1
    log "后端依赖安装完成"
}

frontend_needs_build() {
    ! node scripts/frontend_cache.mjs check-build
}

build_frontend() {
    if ! node scripts/frontend_cache.mjs check-deps; then
        log "安装前端依赖..."
        (cd web && npm ci) || err "npm ci 失败"
        node scripts/frontend_cache.mjs mark-deps || err "前端依赖状态记录失败"
    else
        log "前端依赖未变化，跳过安装"
    fi

    if frontend_needs_build; then
        log "构建前端..."
        (cd web && npm run build) || err "前端构建失败"
        node scripts/frontend_cache.mjs mark-build || err "前端构建状态记录失败"
        log "前端构建完成 -> static-build/"
    else
        log "前端已是最新，跳过构建"
    fi
}

assert_port_free() {
    local port="$1"
    python3 - "$port" <<'PY' || err "端口 ${port} 已被占用，请停止占用进程或修改 APP_PORT"
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        raise SystemExit(1)
PY
}

main() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ViNote v${VERSION} 启动"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    check_deps
    setup_env
    validate_config
    install_backend
    build_frontend
    assert_port_free "$APP_PORT"

    log "启动 ViNote -> http://${APP_HOST}:${APP_PORT}"
    echo ""

    uv run uvicorn backend.main:app --host "$APP_HOST" --port "$APP_PORT" --log-level warning &
    local main_pid="$!"
    PIDS+=("$main_pid")
    wait "$main_pid"
}

main "$@"
