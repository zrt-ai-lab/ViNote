@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
set "VIRTUAL_ENV="
set "VERSION=1.4.0"

if exist VERSION (
    for /f "usebackq delims=" %%v in ("VERSION") do (
        set "VERSION=%%v"
        goto :version_read
    )
)
:version_read

echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo   ViNote v%VERSION% 启动
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

call :check_deps || goto :fail
call :setup_env || goto :fail
call :read_config || goto :fail
call :install_backend || goto :fail
call :build_frontend || goto :fail
call :assert_port_free "%APP_PORT%" || goto :fail

echo [√] 启动 ViNote -^> http://%APP_HOST%:%APP_PORT%
echo.
uv run uvicorn backend.main:app --host "%APP_HOST%" --port "%APP_PORT%" --log-level warning
set "EXIT_CODE=%ERRORLEVEL%"
exit /b %EXIT_CODE%

:fail
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" set "EXIT_CODE=1"
exit /b %EXIT_CODE%

:check_deps
where python >nul 2>&1
if errorlevel 1 (
    echo [X] 需要 Python 3.10+，请先安装 python
    exit /b 1
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo [X] Python 版本过低，需要 3.10+
    exit /b 1
)
where uv >nul 2>&1
if errorlevel 1 (
    echo [X] 需要 uv，请先安装: https://docs.astral.sh/uv/
    exit /b 1
)
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo [X] 需要 FFmpeg，请先安装: https://ffmpeg.org/download.html
    exit /b 1
)
where node >nul 2>&1
if errorlevel 1 (
    echo [X] 需要 Node.js 20.19+ 或 22.12+
    exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
    echo [X] 需要 npm，请确认 Node.js 安装完整
    exit /b 1
)
node -e "const [major, minor] = process.versions.node.split('.').map(Number); process.exit(((major === 20 && minor >= 19) || (major === 22 && minor >= 12) || major > 22) ? 0 : 1)"
if errorlevel 1 (
    for /f "delims=" %%v in ('node -p "process.versions.node"') do set "NODE_VERSION=%%v"
    echo [X] Node.js !NODE_VERSION! 不满足要求，需要 20.19+ 或 22.12+
    exit /b 1
)
for /f "delims=" %%v in ('python -c "import sys; print(str(sys.version_info.major)+'.'+str(sys.version_info.minor))"') do set "PYVER=%%v"
for /f "delims=" %%v in ('node -p "process.versions.node"') do set "NODEVER=%%v"
echo [√] Python %PYVER% ^| Node %NODEVER% ^| ffmpeg 已就绪
exit /b 0

:setup_env
if not exist .env (
    if not exist .env.example (
        echo [X] .env 和 .env.example 均不存在
        exit /b 1
    )
    copy .env.example .env >nul
    echo [!] .env 不存在，已从 .env.example 复制。请编辑 .env 后重新运行 start.bat
    echo [!] 基础界面可在 OPENAI_API_KEY 为空时启动，但 AI 生成能力不可用
    exit /b 2
)
echo [√] .env 已就绪
exit /b 0

:read_config
set "APP_HOST=127.0.0.1"
set "APP_PORT=8999"
set "ASR_PROVIDER=whisper"
set "OPENAI_API_KEY_VALUE="
for /f "tokens=1,* delims==" %%a in ('findstr /r /b /c:"APP_HOST=" /c:"APP_PORT=" /c:"ASR_PROVIDER=" /c:"OPENAI_API_KEY=" .env 2^>nul') do (
    if "%%a"=="APP_HOST" set "APP_HOST=%%b"
    if "%%a"=="APP_PORT" set "APP_PORT=%%b"
    if "%%a"=="ASR_PROVIDER" set "ASR_PROVIDER=%%b"
    if "%%a"=="OPENAI_API_KEY" set "OPENAI_API_KEY_VALUE=%%b"
)
powershell -NoProfile -Command "$p=0; if(-not [int]::TryParse($env:APP_PORT, [ref]$p) -or $p -lt 1 -or $p -gt 65535){exit 1}"
if errorlevel 1 (
    echo [X] APP_PORT 必须是 1-65535 的数字
    exit /b 1
)
if "%OPENAI_API_KEY_VALUE%"=="" (
    echo [!] OPENAI_API_KEY 为空，AI 总结、问答和翻译功能不可用
)
exit /b 0

:install_backend
echo [√] 使用 uv 安装后端依赖...
set "UV_EXTRAS="
if "%ASR_PROVIDER%"=="funasr" set "UV_EXTRAS=--extra funasr"
if "%ASR_PROVIDER%"=="qwen3" set "UV_EXTRAS=--extra qwen3"
if not "%ASR_PROVIDER%"=="whisper" if "%UV_EXTRAS%"=="" (
    echo [X] ASR_PROVIDER 必须为 whisper、funasr 或 qwen3
    exit /b 1
)
uv sync --frozen %UV_EXTRAS%
if errorlevel 1 (
    echo [X] uv sync --frozen 失败
    exit /b 1
)
echo [√] 后端依赖安装完成
set "UV_NO_SYNC=1"
exit /b 0

:build_frontend
node scripts\frontend_cache.mjs check-deps
if not errorlevel 1 goto :frontend_deps_ready
echo [√] 安装前端依赖...
pushd web
call npm ci
if errorlevel 1 (
    popd
    echo [X] npm ci 失败
    exit /b 1
)
popd
node scripts\frontend_cache.mjs mark-deps || exit /b 1
:frontend_deps_ready
node scripts\frontend_cache.mjs check-build
if not errorlevel 1 (
    echo [√] 前端已是最新，跳过构建
    exit /b 0
)
pushd web
call npm run build
if errorlevel 1 (
    popd
    echo [X] 前端构建失败
    exit /b 1
)
popd
node scripts\frontend_cache.mjs mark-build || exit /b 1
echo [√] 前端构建完成 -^> static-build\
exit /b 0

:assert_port_free
set "CHECK_PORT=%~1"
powershell -NoProfile -Command "$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Parse('127.0.0.1'), [int]$env:CHECK_PORT); try { $listener.Start(); $listener.Stop(); exit 0 } catch { exit 1 }"
if errorlevel 1 (
    echo [X] 端口 %CHECK_PORT% 已被占用，请停止占用进程或修改配置
    exit /b 1
)
exit /b 0
