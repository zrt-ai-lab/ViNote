# ============================================
# ViNote Docker 多阶段构建
# ============================================

# ---------- Stage 1: 前端构建 ----------
FROM node:20-alpine AS frontend-builder

WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --silent

COPY web/ ./
RUN npm run build

# ---------- Stage 2: 后端运行环境 ----------
FROM python:3.11-slim AS runtime

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv (高性能 Python 包管理器)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# 复制项目配置文件和最小源码结构（uv sync 需要）
COPY pyproject.toml uv.lock README.md ./
COPY backend/__init__.py ./backend/__init__.py

# 安装 Python 依赖（利用 Docker 层缓存）
RUN uv sync --frozen --no-dev --no-editable

# 复制后端代码（覆盖之前的最小结构）
COPY backend/ ./backend/

# 从前端构建阶段复制静态文件
COPY --from=frontend-builder /app/static-build ./static-build/

# 复制其他必要文件
COPY .env.example ./
COPY cookies.txt.example ./

# 创建数据目录
RUN mkdir -p /app/temp/downloads /app/temp/backups /app/data

# 更新 yt-dlp 到最新版（视频下载依赖最新版本解析）
RUN uv run python -m pip install --upgrade yt-dlp 2>/dev/null || true

# 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8999

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8999/health || exit 1

# 启动命令
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8999", "--log-level", "warning"]
