@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

cd /d "%~dp0"
set "VIRTUAL_ENV="

echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   ViNote v1.3.0 启动
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

:: ========== 检查依赖 ==========
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] 需要 python，请先安装
    pause & exit /b 1
)
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] 需要 ffmpeg，请先安装: https://ffmpeg.org/download.html
    pause & exit /b 1
)

for /f "delims=" %%v in ('python -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))"') do set "PYVER=%%v"
for /f "tokens=3" %%v in ('ffmpeg -version 2^>^&1 ^| findstr /b "ffmpeg version"') do set "FFVER=%%v"
echo [√] Python %PYVER% ^| ffmpeg %FFVER%

:: ========== 环境变量 ==========
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo [!] .env 不存在，已从 .env.example 复制，请编辑填写 OPENAI_API_KEY
    ) else (
        echo [X] .env 和 .env.example 均不存在
        pause & exit /b 1
    )
)
echo [√] .env 已就绪

:: ========== 安装后端依赖 ==========
where uv >nul 2>&1
if !errorlevel! equ 0 (
    echo [√] 使用 uv 安装后端依赖...
    uv sync --quiet
) else (
    echo [√] 使用 pip 安装后端依赖...
    python -m pip install -e "." --quiet
)
echo [√] 后端依赖安装完成

:: ========== 构建前端 ==========
where node >nul 2>&1
if !errorlevel! neq 0 (
    echo [!] 跳过前端构建（未安装 node）
    goto :start_anp
)

if not exist "web\node_modules" (
    echo [√] 安装前端依赖...
    pushd web
    call npm install --silent
    popd
)

if not exist "static-build\index.html" (
    echo [√] 构建前端...
    pushd web
    call npm run build --silent
    popd
    echo [√] 前端构建完成 → static-build\
) else (
    echo [√] 前端已是最新，跳过构建
)

:: ========== ANP 服务（可选） ==========
:start_anp
set "SEARCH_PROVIDERS=local"
if exist .env (
    for /f "tokens=1,* delims==" %%a in ('findstr /b "VIDEO_SEARCH_PROVIDERS" .env 2^>nul') do set "SEARCH_PROVIDERS=%%b"
)

echo !SEARCH_PROVIDERS! | findstr /i "anp" >nul 2>&1
if !errorlevel! equ 0 (
    if exist "backend\anp" (
        if not exist "backend\anp\did_keys\video_search\did.json" (
            echo [√] 生成 ANP DID 密钥...
            pushd backend\anp
            python gen_did_keys.py
            popd
        )

        echo [√] 启动 DID 认证服务器...
        start /b "" python backend\anp\client_did_server.py
        timeout /t 2 /nobreak >nul

        echo [√] 启动 ANP 搜索服务...
        start /b "" python backend\anp\search_server_agent.py
        timeout /t 2 /nobreak >nul
    ) else (
        echo [!] backend\anp 目录不存在，跳过 ANP 服务
    )
)

:: ========== 读取端口配置 ==========
set "HOST=0.0.0.0"
set "PORT=8999"
if exist .env (
    for /f "tokens=1,* delims==" %%a in ('findstr /b "APP_HOST" .env 2^>nul') do set "HOST=%%b"
    for /f "tokens=1,* delims==" %%a in ('findstr /b "APP_PORT" .env 2^>nul') do set "PORT=%%b"
)

:: ========== 检查并释放端口 ==========
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":!PORT! " ^| findstr "LISTENING"') do (
    if "%%p" neq "0" (
        echo [!] 端口 !PORT! 被占用（PID: %%p），正在释放...
        taskkill /PID %%p /F >nul 2>&1
    )
)
timeout /t 1 /nobreak >nul

echo [√] 启动 ViNote → http://!HOST!:!PORT!
echo.

:: ========== 启动主服务（前台运行，Ctrl+C 停止） ==========
where uv >nul 2>&1
if !errorlevel! equ 0 (
    uv run uvicorn backend.main:app --host !HOST! --port !PORT!
) else (
    python -m uvicorn backend.main:app --host !HOST! --port !PORT!
)

endlocal
