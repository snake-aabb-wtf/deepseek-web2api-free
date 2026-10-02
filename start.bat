@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title DeepSeek Chat API Proxy Server

:: ============================================================
::  0. 默认配置（可用系统环境变量 PORT / HOST 覆盖）
:: ============================================================
if "%PORT%"=="" set "PORT=8080"
if "%HOST%"=="" set "HOST=127.0.0.1"
set "REQ=requirements.txt"

echo ==================================================
echo    DeepSeek Chat API Proxy 启动器
echo    HOST=%HOST%    PORT=%PORT%
echo ==================================================
echo.

:: ============================================================
::  1. 定位系统 Python（需 3.10+）
:: ============================================================
set "PYTHON="
where python >nul 2>&1 && set "PYTHON=python"
if not defined PYTHON where py >nul 2>&1 && set "PYTHON=py"
if not defined PYTHON goto :no_python
"%PYTHON%" --version >nul 2>&1 || goto :no_python
"%PYTHON%" -c "import sys;sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1 || goto :old_python
for /f "tokens=*" %%v in ('"%PYTHON%" --version 2^>^&1') do set "PYVER=%%v"
echo [1/6] 系统 Python: !PYVER!
echo.

:: ============================================================
::  2. 查找或创建虚拟环境（优先 .venv，其次 venv / env）
:: ============================================================
set "VENV="
if exist ".venv\Scripts\python.exe" set "VENV=.venv"
if not defined VENV if exist "venv\Scripts\python.exe" set "VENV=venv"
if not defined VENV if exist "env\Scripts\python.exe" set "VENV=env"
if defined VENV (
    echo [2/6] 检测到虚拟环境: %VENV%
) else (
    echo [2/6] 未找到虚拟环境，正在创建 .venv ...
    "%PYTHON%" -m venv .venv
    if errorlevel 1 (
        echo        创建 .venv 失败，尝试 venv ...
        "%PYTHON%" -m venv venv
        if errorlevel 1 goto :venv_failed
        set "VENV=venv"
    ) else (
        set "VENV=.venv"
    )
    echo        虚拟环境已创建: !VENV!
)
set "PY=%VENV%\Scripts\python.exe"
if not exist "%PY%" goto :venv_failed
echo.

:: ============================================================
::  3. 校验依赖（不足则自动安装）
:: ============================================================
set "CHK=%TEMP%\ds2api_pipchk_%RANDOM%.txt"
echo [3/6] 正在校验 %VENV% 中的依赖 ...
"%PY%" -m pip install --dry-run -r "%REQ%" > "%CHK%" 2>&1
set "DRY_RC=!errorlevel!"
findstr /i "would install" "%CHK%" >nul 2>&1
set "NEED=!errorlevel!"
del "%CHK%" >nul 2>&1
if !DRY_RC! equ 0 if !NEED! equ 1 (
    echo        依赖已齐全，跳过安装。
) else (
    echo        依赖缺失或校验失败，正在安装 ...
    if !DRY_RC! neq 0 echo        （pip 校验未通过——可能离线或 pip 过旧，将直接安装）
    "%PY%" -m pip install --upgrade pip >nul 2>&1
    "%PY%" -m pip install -r "%REQ%"
    if errorlevel 1 goto :deps_failed
    echo        依赖安装完成。
)
echo.

:: ============================================================
::  4. 构建 WebUI（v3.0.0 React 账号池管理面板）
:: ============================================================
set "WEBUI_DIR=webui-new"
set "WEBUI_DIST=%WEBUI_DIR%\dist"
set "NEED_BUILD=1"
if exist "%WEBUI_DIST%\index.html" if not defined WEBUI_REBUILD set "NEED_BUILD=0"
echo [4/6] 检查 WebUI 构建产物 ...
if "!NEED_BUILD!"=="0" (
    echo        WebUI 已构建，跳过构建（强制重建请先执行: set WEBUI_REBUILD=1）。
) else (
    if defined WEBUI_REBUILD (
        echo        检测到 WEBUI_REBUILD，强制重新构建 ...
    ) else (
        echo        未找到构建产物，开始构建 ...
    )
    where node >nul 2>&1
    if errorlevel 1 (
        echo        [警告] 未找到 node/npm，无法构建 WebUI。
        echo        仅启动后端 API；稍后可运行 %WEBUI_DIR%\scripts\build.bat 手动构建。
    ) else (
        pushd "%WEBUI_DIR%"
        call scripts\build.bat
        set "BUILD_RC=!errorlevel!"
        popd
        if !BUILD_RC! neq 0 (
            echo        [警告] WebUI 构建失败，仅启动后端 API。
            echo        可稍后运行 %WEBUI_DIR%\scripts\build.bat 重试。
        ) else (
            echo        WebUI 构建完成: %WEBUI_DIST%
        )
    )
)
echo.
:: ============================================================
::  5. 释放端口（只杀本项目的进程，绝不误杀他人）
:: ============================================================
echo [5/6] 检查端口 %PORT% ...
set "BLOCKED="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
    set "PID=%%a"
    set "CMDLINE="
    for /f "usebackq tokens=*" %%c in (`powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter 'ProcessId=%%a').CommandLine" 2^>nul`) do set "CMDLINE=%%c"
    if defined CMDLINE (
        echo        端口 %PORT% 被 PID !PID! 占用，命令行: !CMDLINE!
        echo !CMDLINE! | findstr /i "uvicorn server:app server.py ds2api" >nul
        if !errorlevel! equ 0 (
            echo        是本项目进程，结束它 ...
            taskkill /F /PID !PID! >nul 2>&1
            if !errorlevel! neq 0 taskkill /F /T /PID !PID! >nul 2>&1
            ping -n 2 127.0.0.1 >nul
        ) else (
            echo        该进程与本项目无关，拒绝结束。
            set "BLOCKED=1"
        )
    ) else (
        echo        端口 %PORT% 被 PID !PID! 占用，但无法读取其命令行，拒绝自动结束。
        set "BLOCKED=1"
    )
)
if defined BLOCKED (
    echo.
    echo   ============================================================
    echo   端口 %PORT% 被其他进程占用，且不是本服务。
    echo   请自行释放端口，或换一个端口启动：
    echo       set PORT=9090 ^&^& start.bat
    echo   ============================================================
    echo.
    pause
    exit /b 1
)
echo.

:: ============================================================
::  6. 启动服务
:: ============================================================
echo [6/6] 正在启动服务 %HOST%:%PORT% ...
echo.
:: 访问地址：0.0.0.0 / :: 是监听地址，浏览器应访问 127.0.0.1
set "ACCESS_HOST=%HOST%"
if "%ACCESS_HOST%"=="0.0.0.0" set "ACCESS_HOST=127.0.0.1"
echo.
echo   ============================================================
echo   服务启动后可通过以下地址访问：
echo      WebUI 管理面板:  http://%ACCESS_HOST%:%PORT%/webui/
echo      OpenAI API:      http://%ACCESS_HOST%:%PORT%/v1/chat/completions
echo      健康检查:        http://%ACCESS_HOST%:%PORT%/health
echo   管理密码: 见 .env 中 DEEPSEEK_ADMIN_PASSWORD 设置
echo   ============================================================
echo.
if not "%WEBUI_OPEN%"=="0" (
    echo   3 秒后自动打开浏览器（跳过自动打开请先执行: set WEBUI_OPEN=0）
    start "" powershell -NoProfile -Command "Start-Sleep -Seconds 3; Start-Process 'http://%ACCESS_HOST%:%PORT%/webui/'"
) else (
    echo   已跳过自动打开浏览器（WEBUI_OPEN=0）。
)
echo.
"%PY%" -m uvicorn server:app --host %HOST% --port %PORT%
if errorlevel 1 (
    echo.
    echo   服务异常退出，请查看上方日志。
    pause
)
exit /b %errorlevel%

:: ---------- 错误处理 ----------
:no_python
echo.
echo [错误] 未找到 Python 3.10+（已尝试 "python" 和 "py"）。
echo        请从 https://www.python.org/downloads/ 安装并加入 PATH。
pause
exit /b 1

:old_python
echo.
echo [错误] 需要 Python 3.10+，当前版本:
"%PYTHON%" --version
pause
exit /b 1

:venv_failed
echo.
echo [错误] 虚拟环境创建/使用失败。
echo        可手动执行: "%PYTHON%" -m venv .venv
pause
exit /b 1

:deps_failed
echo.
echo [错误] 依赖安装失败，请查看上方日志。
echo        可手动执行: "%PY%" -m pip install -r "%REQ%"
pause
exit /b 1
