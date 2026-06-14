@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
echo Baiou miniprogram API: http://127.0.0.1:7871
python -m baiou.product.api.serve
pause
