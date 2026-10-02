@echo off
REM build_webui.bat — install deps + build the React webui
setlocal enabledelayedexpansion
cd /d "%~dp0\.."

set "NEED_INSTALL=0"
if not exist "node_modules\.bin\tsc.cmd" set "NEED_INSTALL=1"
if not exist "node_modules\.bin\vite.cmd" set "NEED_INSTALL=1"

if "!NEED_INSTALL!"=="1" (
  if exist pnpm-lock.yaml (
    echo ==^> pnpm install
    call pnpm install --frozen-lockfile=false
  ) else (
    if exist package-lock.json (
      echo ==^> npm ci
      call npm ci --no-audit --no-fund
    ) else (
      echo ==^> npm install
      call npm install --no-audit --no-fund
    )
  )
  set "INSTALL_RC=!errorlevel!"
  if not "!INSTALL_RC!"=="0" (
    echo.
    echo ERROR: dependency installation failed. Check npm registry/proxy connectivity and retry.
    exit /b !INSTALL_RC!
  )
)

set "TOOLS_MISSING=0"
if not exist "node_modules\.bin\tsc.cmd" set "TOOLS_MISSING=1"
if not exist "node_modules\.bin\vite.cmd" set "TOOLS_MISSING=1"
if "!TOOLS_MISSING!"=="1" (
  echo.
  echo ERROR: tsc or vite is missing after dependency installation.
  exit /b 1
)

if exist pnpm-lock.yaml (
  echo ==^> pnpm run build
  call pnpm run build
) else (
  echo ==^> npm run build
  call npm run build
)
set "BUILD_RC=!errorlevel!"
if not "!BUILD_RC!"=="0" exit /b !BUILD_RC!

echo.
echo Build complete: webui-new\dist\
dir /b dist\
exit /b 0
