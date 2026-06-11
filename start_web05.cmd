@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=D:\python312\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo.
echo Starting Qingsheng local web console...
echo Project: %CD%
echo Python: %PYTHON_EXE%
echo.
echo Open this URL after startup: http://127.0.0.1:7860
echo Keep this window open. Closing it will stop the web server.
echo.

"%PYTHON_EXE%" -m workflow.qingsheng_skill_web05.serve

echo.
echo Web server stopped.
pause
