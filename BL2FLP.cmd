@echo off
setlocal
cd /d "%~dp0"
python -m bl2flp %*
if errorlevel 1 pause
