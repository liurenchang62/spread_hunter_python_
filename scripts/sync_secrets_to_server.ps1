#Requires -Version 5.1
<#
  Sync gitignored secrets to VPS over SSH (key-based auth recommended).

  Security: uploads API keys, withdrawal addresses, trader/config.py — only on trusted PC + server.
  Default host 45.76.202.248; override: -Server x.x.x.x or env SPREAD_HUNTER_SERVER.

  Usage (repo root):
    powershell -ExecutionPolicy Bypass -File .\scripts\sync_secrets_to_server.ps1
#>
param(
    [string] $Server = $(if ($env:SPREAD_HUNTER_SERVER) { $env:SPREAD_HUNTER_SERVER } else { "45.76.202.248" }),
    [string] $User = "root",
    [string] $RemoteBase = "/root/spread_hunter_python"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

$relFiles = @(
    "clients\api_keys_demo.py",
    "clients\api_keys_live.py",
    "clients\withdrawal_addresses.py",
    "trader\config.py",
    "clients\api_keys.py"
)

$uploadedRemote = New-Object System.Collections.Generic.List[string]

foreach ($rel in $relFiles) {
    $local = Join-Path $RepoRoot $rel
    if (-not (Test-Path -LiteralPath $local)) {
        Write-Host "SKIP missing: $rel"
        continue
    }
    $dir = Split-Path -Parent $rel
    $remoteDir = ($dir -replace "\\", "/")
    $dest = "${User}@${Server}:${RemoteBase}/${remoteDir}/"
    Write-Host "UPLOAD: $rel -> $dest"
    & scp -q $local $dest
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed: $local"
    }
    $leaf = Split-Path $rel -Leaf
    $uploadedRemote.Add("${RemoteBase}/${remoteDir}/${leaf}")
}

if ($uploadedRemote.Count -eq 0) {
    Write-Warning "No files uploaded. Create api_keys_*.py, withdrawal_addresses.py, trader\config.py locally first."
    exit 1
}

$remoteList = $uploadedRemote -join " "
Write-Host "SSH: chmod 600 on server ${User}@${Server} ..."
& ssh -q "${User}@${Server}" "chmod 600 $remoteList"
if ($LASTEXITCODE -ne 0) {
    throw "ssh chmod failed. On server run: chmod 600 $remoteList"
}

Write-Host "DONE: $($uploadedRemote.Count) file(s) -> ${User}@${Server}:${RemoteBase}"
