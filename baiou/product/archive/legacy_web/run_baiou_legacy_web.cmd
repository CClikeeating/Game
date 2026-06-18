@echo off
cd /d "%~dp0\..\..\..\.."
set PYTHONUTF8=1
echo Baiou legacy debug web: http://127.0.0.1:7870
python -m baiou.product.archive.legacy_web.serve
pause
