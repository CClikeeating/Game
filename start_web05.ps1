$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root

$Python = "D:\python312\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    $PythonCommand = Get-Command python -ErrorAction Stop
    $Python = $PythonCommand.Source
}

$Port = 7860
$Existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($Existing) {
    Write-Host "端口 $Port 已经有服务在运行。" -ForegroundColor Yellow
    Write-Host "请直接打开：http://127.0.0.1:$Port"
    Write-Host "如果页面打不开，请先关闭占用该端口的进程后再运行本脚本。"
    pause
    exit 0
}

Write-Host ""
Write-Host "Qingsheng 本地测试台启动中..." -ForegroundColor Cyan
Write-Host "项目目录：$Root"
Write-Host "Python：$Python"
Write-Host ""
Write-Host "启动成功后请打开：http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "注意：这个窗口不要关闭，关闭后网页服务会停止。"
Write-Host ""

& $Python -m workflow.qingsheng_skill_web05.serve

Write-Host ""
Write-Host "网页服务已停止。"
pause
