@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
python -m workV.web.serve
pause
