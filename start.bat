@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
set "VIRTUAL_ENV="
set "VERSION=1.4.0"
set "PIDS="

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
call :start_anp || goto :fail

echo [√] 启动 ViNote -^> http://%APP_HOST%:%APP_PORT%
echo.
uv run uvicorn backend.main:app --host "%APP_HOST%" --port "%APP_PORT%" --log-level warning
set "EXIT_CODE=%ERRORLEVEL%"
call :cleanup
exit /b %EXIT_CODE%

:fail
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" set "EXIT_CODE=1"
call :cleanup
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
set "APP_HOST=0.0.0.0"
set "APP_PORT=8999"
set "VIDEO_SEARCH_PROVIDERS=local"
set "OPENAI_API_KEY_VALUE="
for /f "tokens=1,* delims==" %%a in ('findstr /r /b /c:"APP_HOST=" /c:"APP_PORT=" /c:"VIDEO_SEARCH_PROVIDERS=" /c:"OPENAI_API_KEY=" .env 2^>nul') do (
    if "%%a"=="APP_HOST" set "APP_HOST=%%b"
    if "%%a"=="APP_PORT" set "APP_PORT=%%b"
    if "%%a"=="VIDEO_SEARCH_PROVIDERS" set "VIDEO_SEARCH_PROVIDERS=%%b"
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
uv sync --frozen
if errorlevel 1 (
    echo [X] uv sync --frozen 失败
    exit /b 1
)
echo [√] 后端依赖安装完成
exit /b 0

:build_frontend
echo [√] 安装前端依赖...
pushd web
npm ci
if errorlevel 1 (
    popd
    echo [X] npm ci 失败
    exit /b 1
)
npm run build
if errorlevel 1 (
    popd
    echo [X] 前端构建失败
    exit /b 1
)
popd
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

:provider_enabled
echo,%VIDEO_SEARCH_PROVIDERS%, | findstr /i /c:",%~1," >nul 2>&1
exit /b %ERRORLEVEL%

:wait_http
set "WAIT_URL=%~1"
set "WAIT_NAME=%~2"
set "WAIT_TIMEOUT=%~3"
powershell -NoProfile -Command "$deadline=(Get-Date).AddSeconds([int]$env:WAIT_TIMEOUT); do { try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 $env:WAIT_URL; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 500){exit 0} } catch {}; Start-Sleep -Seconds 1 } while((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
    echo [X] %WAIT_NAME% 未在限定时间内就绪
    exit /b 1
)
exit /b 0

:start_anp
call :provider_enabled anp
if errorlevel 1 exit /b 0
if not exist "backend\anp" (
    echo [X] VIDEO_SEARCH_PROVIDERS 启用了 anp，但 backend\anp 不存在
    exit /b 1
)
call :assert_port_free 9000 || exit /b 1
call :assert_port_free 8000 || exit /b 1

if not exist "backend\anp\did_keys\video_search\did.json" (
    echo [√] 生成 ANP DID 密钥...
    pushd backend\anp
    uv run python gen_did_keys.py
    if errorlevel 1 (
        popd
        echo [X] ANP DID 密钥生成失败
        exit /b 1
    )
    popd
)

echo [√] 启动 DID 认证服务器...
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "$p=Start-Process uv -ArgumentList 'run','python','client_did_server.py' -WorkingDirectory 'backend\anp' -PassThru -WindowStyle Hidden; $p.Id"`) do set "DID_PID=%%p"
if "%DID_PID%"=="" (
    echo [X] DID 认证服务器启动失败
    exit /b 1
)
set "PIDS=%PIDS% %DID_PID%"
call :wait_http "http://127.0.0.1:9000/.well-known/did.json" "DID 认证服务器" 30 || exit /b 1

echo [√] 启动 ANP 搜索服务...
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "$p=Start-Process uv -ArgumentList 'run','python','search_server_agent.py' -WorkingDirectory 'backend\anp' -PassThru -WindowStyle Hidden; $p.Id"`) do set "ANP_PID=%%p"
if "%ANP_PID%"=="" (
    echo [X] ANP 搜索服务启动失败
    exit /b 1
)
set "PIDS=%PIDS% %ANP_PID%"
call :wait_http "http://127.0.0.1:8000/health" "ANP 搜索服务" 45 || exit /b 1
exit /b 0

:cleanup
for %%p in (%PIDS%) do (
    taskkill /PID %%p /T /F >nul 2>&1
)
exit /b 0
