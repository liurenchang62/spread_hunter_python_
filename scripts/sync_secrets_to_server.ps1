#Requires -Version 5.1
<#
  将 .gitignore 中的敏感/本地配置一键同步到 VPS（走 SSH，需已配置密钥或 ssh-agent）。

  安全说明（请先读完再执行）：
  - 私密性：会上传 API 密钥、提币地址、trader 参数；仅在你信任本机与目标服务器时执行。
  - 传输：scp/ssh 默认加密；避免在不可信网络下操作。
  - 仓库：若将本脚本中的默认 IP 提交到「公开」GitHub，公网可见你的 VPS 地址（风险低于密钥泄露，但非零）。
         可改 param -Server，或设置环境变量 SPREAD_HUNTER_SERVER，且勿把密钥写进脚本。

  用法（在仓库根目录或任意目录均可，脚本会定位仓库根）：
    powershell -ExecutionPolicy Bypass -File .\scripts\sync_secrets_to_server.ps1
    powershell -ExecutionPolicy Bypass -File .\scripts\sync_secrets_to_server.ps1 -Server "1.2.3.4"
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
        Write-Host "[跳过] 本地不存在: $rel"
        continue
    }
    $dir = Split-Path -Parent $rel
    $remoteDir = ($dir -replace "\\", "/")
    $dest = "${User}@${Server}:${RemoteBase}/${remoteDir}/"
    Write-Host "[上传] $rel -> $dest"
    & scp -q $local $dest
    if ($LASTEXITCODE -ne 0) {
        throw "scp 失败: $local"
    }
    $leaf = Split-Path $rel -Leaf
    $uploadedRemote.Add("${RemoteBase}/${remoteDir}/${leaf}")
}

if ($uploadedRemote.Count -eq 0) {
    Write-Warning "没有上传任何文件（请确认本机已存在 api_keys_*.py / withdrawal_addresses.py / trader\config.py 等）。"
    exit 1
}

$remoteList = $uploadedRemote -join " "
Write-Host "[权限] ssh ${User}@${Server} chmod 600 ..."
& ssh -q "${User}@${Server}" "chmod 600 $remoteList"
if ($LASTEXITCODE -ne 0) {
    throw "ssh chmod 失败，请登录服务器手动: chmod 600 $remoteList"
}

Write-Host "[完成] 已同步 $($uploadedRemote.Count) 个文件到 ${User}@${Server}:${RemoteBase}"
