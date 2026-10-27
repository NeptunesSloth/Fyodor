@echo off
rem Game-night start on Windows: scripts\start.cmd [--local]
setlocal
set ROOT=%~dp0..
set HAVE_PY=0
where py >nul 2>nul && set HAVE_PY=1
where python >nul 2>nul && set HAVE_PY=1
if "%HAVE_PY%"=="0" (
  echo Fyodor needs Python 3.11 or newer: install it from https://www.python.org/downloads/
  echo Tick "Add python.exe to PATH", then double-click Start Fyodor again.
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 if not exist "%ROOT%\frontend\dist\index.html" (
  echo Fyodor needs Node.js the first time: install the LTS from https://nodejs.org, then double-click Start Fyodor again.
  exit /b 1
)
if not exist "%ROOT%\backend\.venv\Scripts\python.exe" (
  echo First run: installing Fyodor ^(one time^)...
  py -3 -m venv "%ROOT%\backend\.venv" || python -m venv "%ROOT%\backend\.venv"
  "%ROOT%\backend\.venv\Scripts\python.exe" -m pip install -e "%ROOT%\backend"
  pushd "%ROOT%\frontend" && call npm install && popd
)
if not exist "%ROOT%\frontend\dist\index.html" (
  pushd "%ROOT%\frontend" && call npm run build && popd
)
cd /d "%ROOT%\backend"
"%ROOT%\backend\.venv\Scripts\python.exe" -m app.launcher %*
