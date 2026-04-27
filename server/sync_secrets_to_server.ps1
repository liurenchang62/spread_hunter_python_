#Requires -Version 5.1
<#
  Sync gitignored secrets to VPS (SSH key auth recommended).

  Uploads if present:
    trader/config.py, trader_config.ref.txt,
    clients/api_keys*.py, withdrawal_addresses.py,
    env/ (recursive)

  Usage (repo root):
    powershell -ExecutionPolicy Bypass -File .\server\sync_secrets_to_server.ps1
    powershell -ExecutionPolicy Bypass -File .\server\sync_secrets_to_server.ps1 -Server "x.x.x.x"
#>
param(
    [string] $Server = $(if ($env:SPREAD_HUNTER_SERVER) { $env:SPREAD_HUNTER_SERVER } else { "45.76.202.248" }),
    [string] $User = "root",
    [string] $RemoteBase = "/root/spread_hunter_python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$remoteHost = ('{0}@{1}' -f $User, $Server)

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
        Write-Host ('SKIP missing: {0}' -f $rel)
        continue
    }
    $dir = Split-Path -Parent $rel
    $remoteDir = ($dir -replace "\\", "/")
    $dest = ('{0}:{1}/{2}/' -f $remoteHost, $RemoteBase, $remoteDir)
    Write-Host ('UPLOAD: {0} -> {1}' -f $rel, $dest)
    & scp -q $local $dest
    if ($LASTEXITCODE -ne 0) {
        throw ('scp failed: {0}' -f $local)
    }
    $leaf = Split-Path $rel -Leaf
    $uploadedForChmod.Add(('{0}/{1}/{2}' -f $RemoteBase, $remoteDir, $leaf))
}

$envLocal = Join-Path $RepoRoot "env"
if (Test-Path -LiteralPath $envLocal) {
    Write-Host ('UPLOAD: env/ -> {0}:{1}/ recursive' -f $remoteHost, $RemoteBase)
    & scp -r -q $envLocal ('{0}:{1}/' -f $remoteHost, $RemoteBase)
    if ($LASTEXITCODE -ne 0) {
        throw 'scp -r env/ failed'
    }
}

if ($uploadedForChmod.Count -eq 0 -and -not (Test-Path -LiteralPath $envLocal)) {
    Write-Warning 'No files uploaded. Create keys, trader\config.py or env\ locally first.'
    exit 1
}

if ($uploadedForChmod.Count -gt 0) {
    $remoteList = ($uploadedForChmod | ForEach-Object { $_ }) -join ' '
    Write-Host ('SSH: chmod 600 on {0}' -f $remoteHost)
    $sshChmod = ('chmod 600 {0}' -f $remoteList)
    & ssh -q $remoteHost $sshChmod
    if ($LASTEXITCODE -ne 0) {
        throw ('ssh chmod failed. On server: chmod 600 {0}' -f $remoteList)
    }
}

if (Test-Path -LiteralPath $envLocal) {
    Write-Host 'SSH: chmod for env directory on server'
    $envChmod = (
        'chmod 700 {0}/env 2>/dev/null || true; test -f {0}/env/.env && chmod 600 {0}/env/.env || true' `
            -f $RemoteBase
    )
    & ssh -q $remoteHost $envChmod
}

Write-Host ('DONE -> {0}:{1}' -f $remoteHost, $RemoteBase)
