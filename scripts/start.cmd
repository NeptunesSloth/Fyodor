@echo off
rem Game-night start on Windows: scripts\start.cmd [--lan]
setlocal
set ROOT=%~dp0..
if not exist "%ROOT%\backend\.venv\Scripts\python.exe" (
  echo First run: installing Fyodor (one time)...
  py -3 -m venv "%ROOT%\backend\.venv" || python -m venv "%ROOT%\backend\.venv"
  "%ROOT%\backend\.venv\Scripts\python.exe" -m pip install -e "%ROOT%\backend"
  pushd "%ROOT%\frontend" && call npm install && popd
)
if not exist "%ROOT%\frontend\dist\index.html" (
  pushd "%ROOT%\frontend" && call npm run build && popd
)
cd /d "%ROOT%\backend"
"%ROOT%\backend\.venv\Scripts\python.exe" -m app.launcher %*
