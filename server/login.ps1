#Requires -Version 5.1
<#
  Open SSH shell to VPS using SERVER_PASSWORD (same vars as sync_to_server.py).
  Repo root:
    powershell -NoProfile -ExecutionPolicy Bypass -File .\server\login.ps1

  Prefer PuTTY plink.exe; fallback OpenSSH ssh.exe.
  Do NOT name variables $plink (splat quirks).
#>

$ErrorActionPreference = 'Stop'

function Read-TrimmedEnv([string]$Name) {
    $raw = [Environment]::GetEnvironmentVariable($Name)
    if ($null -eq $raw) { return $null }
    [string]$t = ('' + $raw).Trim()
    if ([string]::IsNullOrWhiteSpace($t)) { return $null }
    return $t
}

$h = Read-TrimmedEnv 'SERVER_HOST'
if ($null -eq $h) { $h = Read-TrimmedEnv 'SPREAD_HUNTER_SERVER' }
if ($null -eq $h) { $h = '45.76.202.248' }

$acct = Read-TrimmedEnv 'SERVER_USER'
if ($null -eq $acct) { $acct = 'root' }

$portStr = Read-TrimmedEnv 'SERVER_PORT'
if (($null -eq $portStr) -or ($portStr -notmatch '^[0-9]+$')) {
    $portNum = 22
}
else {
    $portNum = [int]::Parse(($portStr + ''))
}

$pwPlain = Read-TrimmedEnv 'SERVER_PASSWORD'
if (($null -eq $pwPlain) -or (($pwPlain + '').Trim().Length -eq 0)) {
    Write-Host 'Set SERVER_PASSWORD in your environment (Windows user or system variables).' -ForegroundColor Red
    exit 1
}
$pwPlain = (($pwPlain + '').Trim())

# Concatenate login id (char 64 separates user and hostname)
$userHost = [string]::Concat(($acct.Trim()), ([string][char]64), ($h.Trim()))

Write-Host ('SSH login {0} port {1}' -f $userHost, $portNum) -ForegroundColor Green

function Locate-PlinkExe {
    $p1 = Join-Path $env:ProgramFiles 'PuTTY\plink.exe'
    if ((Test-Path -LiteralPath $p1)) {
        return (((Resolve-Path -LiteralPath $p1).ProviderPath) + '').Trim()
    }
    [string]$px86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
    if ((-not ([string]::IsNullOrWhiteSpace(($px86 + '')))) -and (($px86 + '').Trim().Length -gt 2)) {
        $p2 = Join-Path $px86 'PuTTY\plink.exe'
        if ((Test-Path -LiteralPath $p2)) {
            return (((Resolve-Path -LiteralPath $p2).ProviderPath) + '').Trim()
        }
    }
    foreach ($n in @( 'plink.exe', 'plink' )) {
        foreach ($wc in @( Get-Command -Name $n -CommandType Application -ErrorAction SilentlyContinue )) {
            if (($null -eq $wc) -or (($wc.Source + '').Trim().Length -lt 10)) {
                continue
            }
            [string]$pth = (($wc.Source) + '').Trim()
            if ($pth.ToLowerInvariant().EndsWith('plink.exe')) {
                return $pth.Trim()
            }
        }
    }
    return ''
}

[string]$plinkPath = Locate-PlinkExe
[string]$plinkPath = (($plinkPath + '').Trim())

if ((-not ([string]::IsNullOrWhiteSpace($plinkPath)))) {
    [System.Diagnostics.Process]$plinkProc = Start-Process -FilePath (($plinkPath + '').Trim()) -ArgumentList @(
        '-ssh', (($userHost + '')),
        '-P', (($portNum.ToString())),
        '-pw', (($pwPlain + '')),
        '-t'
    ) -NoNewWindow -PassThru -Wait -ErrorAction Continue
    if (($null -ne $plinkProc) -and ($null -ne $plinkProc.ExitCode)) {
        exit [int]$plinkProc.ExitCode
    }
    exit 1

}

Write-Host 'plink.exe not found. Falling back to ssh.exe (key or interactive password may be required).' `
    -ForegroundColor Yellow

Write-Host ('ssh -p {0} {1}' -f ($portNum + ''), (($userHost + ''))) `
    -ForegroundColor Yellow

Start-Process -FilePath 'ssh.exe' -ArgumentList @(
    '-p', (($portNum.ToString())), (($userHost + ''))
) -NoNewWindow -Wait -ErrorAction Continue
exit $LASTEXITCODE
