@echo off
rem Double-click to host game night on Windows: installs on the first run, downloads the cards,
rem starts Fyodor and opens the table. Friends on your network open the address it shows.
call "%~dp0scripts\start.cmd" %*
pause
