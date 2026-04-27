#Requires -Version 5.1
<#
  将本机「不进 Git」的敏感与本地配置一次性同步到 VPS（建议 SSH 公钥登录）。

  覆盖范围与 .gitignore 中典型项对齐（存在才上传，缺失则 SKIP）：
    - clients/api_keys.py, api_keys_live.py, api_keys_demo.py
    - clients/withdrawal_addresses.py
    - trader/config.py
    - trader_config.ref.txt（与服务器对比参数用，可选）
    - env/ 整个目录（若存在，如 env/.env）

  用法（仓库根目录）：
    powershell -ExecutionPolicy Bypass -File .\scripts\sync_secrets_to_server.ps1
    powershell -ExecutionPolicy Bypass -File .\scripts\sync_secrets_to_server.ps1 -Server "你的IP"
  或环境变量：$env:SPREAD_HUNTER_SERVER = "x.x.x.x"
#>
param(
    [string] $Server = $(if ($env:SPREAD_HUNTER_SERVER) { $env:SPREAD_HUNTER_SERVER } else { "45.76.202.248" }),
    [string] $User = "root",
    [string] $RemoteBase = "/root/spread_hunter_python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$remoteHost = "${User}@${Server}"

# 顺序：与 SERVER_COMMANDS 文档一致，便于对照
$relFiles = @(
    "trader\config.py",
    "trader_config.ref.txt",
    "clients\api_keys_live.py",
    "clients\api_keys_demo.py",
    "clients\withdrawal_addresses.py",
    "clients\api_keys.py"
)

$uploadedForChmod = New-Object System.Collections.Generic.List[string]

foreach ($rel in $relFiles) {
    $local = Join-Path $RepoRoot $rel
    if (-not (Test-Path -LiteralPath $local)) {
        Write-Host "SKIP missing: $rel"
        continue
    }
    $dir = Split-Path -Parent $rel
    $remoteDir = ($dir -replace "\\", "/")
    $dest = "${remoteHost}:${RemoteBase}/${remoteDir}/"
    Write-Host "UPLOAD: $rel -> $dest"
    & scp -q $local $dest
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed: $local"
    }
    $leaf = Split-Path $rel -Leaf
    $uploadedForChmod.Add("${RemoteBase}/${remoteDir}/${leaf}")
}

$envLocal = Join-Path $RepoRoot "env"
if (Test-Path -LiteralPath $envLocal) {
    Write-Host "UPLOAD: env/ -> ${remoteHost}:${RemoteBase}/ (recursive)"
    & scp -r -q $envLocal "${remoteHost}:${RemoteBase}/"
    if ($LASTEXITCODE -ne 0) {
        throw "scp -r env/ failed"
    }
}

if ($uploadedForChmod.Count -eq 0 -and -not (Test-Path -LiteralPath $envLocal)) {
    Write-Warning "No files uploaded. 请先在本机创建密钥、trader\config.py 或 env/ 后再执行。"
    exit 1
}

if ($uploadedForChmod.Count -gt 0) {
    $remoteList = ($uploadedForChmod | ForEach-Object { $_ }) -join " "
    Write-Host "SSH: chmod 600 (sensitive files) on $remoteHost ..."
    & ssh -q $remoteHost "chmod 600 $remoteList"
    if ($LASTEXITCODE -ne 0) {
        throw "ssh chmod failed. On server run: chmod 600 $remoteList"
    }
}

if (Test-Path -LiteralPath $envLocal) {
    Write-Host "SSH: chmod 700 env + 600 env/.env (if present) ..."
    $envChmod = "chmod 700 ${RemoteBase}/env 2>/dev/null || true; test -f ${RemoteBase}/env/.env && chmod 600 ${RemoteBase}/env/.env || true"
    & ssh -q $remoteHost $envChmod
}

Write-Host "DONE -> ${remoteHost}:${RemoteBase}"
