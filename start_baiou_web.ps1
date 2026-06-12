$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $Root
$env:PYTHONUTF8 = "1"
python -m baiou.product.web.serve
