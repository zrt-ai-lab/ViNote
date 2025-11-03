#!/bin/bash

# 启动脚本：同时运行 DID 服务器、ANP 搜索服务端和主应用

set -e  # 遇到错误立即退出

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "📍 工作目录: $SCRIPT_DIR"

# 生成 DID 密钥（如果不存在）
if [ ! -f "backend/anp/did_keys/video_search/did.json" ]; then
    echo "🔑 生成 ANP DID 密钥..."
    (cd backend/anp && python gen_did_keys.py)
fi

# 启动 DID 认证服务器（后台运行）
echo "🚀 启动 DID 认证服务器..."
(cd backend/anp && python client_did_server.py) &
DID_PID=$!

# 等待 DID 服务器启动
sleep 3

# 启动视频搜索服务端（后台运行）
echo "🔍 启动视频搜索服务端..."
(cd backend/anp && python search_server_agent.py) &
SEARCH_PID=$!

# 等待搜索服务端启动
sleep 3

# 启动主应用（前台运行）
echo "🎉 启动 ViNote 主应用..."
uvicorn backend.main:app --host 0.0.0.0 --port 8999 &
MAIN_PID=$!

# 捕获退出信号，清理所有进程
trap "echo '🛑 停止所有服务...'; kill $DID_PID $SEARCH_PID $MAIN_PID 2>/dev/null; exit" SIGTERM SIGINT EXIT

echo "✅ 所有服务已启动！"
echo "📊 进程 ID - DID: $DID_PID, 搜索: $SEARCH_PID, 主应用: $MAIN_PID"

# 等待主应用
wait $MAIN_PID
