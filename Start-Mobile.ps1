$ErrorActionPreference = 'Stop'
$env:BJJVAULT_ROOT = $PSScriptRoot
$env:PYTHONUTF8 = '1'
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot '.tools'), (Join-Path $PSScriptRoot 'data\logs') | Out-Null
'enabled' | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'data\mobile-enabled')
$statePath = Join-Path $PSScriptRoot 'data\mobile-processes.json'
$urlPath = Join-Path $PSScriptRoot 'data\mobile-url.json'
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $running = Get-CimInstance Win32_Process -Filter "ProcessId=$($state.supervisor_pid)"
    if ($running -and $running.CommandLine -match 'bjjvault.mobile_access') {
        Write-Host 'Mobile clip access is already running.'
        if (Test-Path -LiteralPath $urlPath) { Write-Host ((Get-Content -LiteralPath $urlPath -Raw | ConvertFrom-Json).url) }
        return
    }
}
$binary = Join-Path $PSScriptRoot '.tools\cloudflared.exe'
$expectedHash = '86aee4017b26625cee8484c113558f48effa4cd47f7aa05fcf425604e5d2b23c'
if (!(Test-Path -LiteralPath $binary)) {
    Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/download/2026.10.0/cloudflared-windows-amd64.exe' -OutFile $binary
}
if ((Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLower() -ne $expectedHash) {
    throw 'Cloudflared checksum mismatch; replace it with the pinned official release.'
}
Start-Process -FilePath (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -ArgumentList '-X utf8 -m bjjvault.mobile_access' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'data\logs\mobile.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'data\logs\mobile.stderr.log') | Out-Null
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if (Test-Path -LiteralPath $urlPath) {
        Write-Host ('Mobile clip access: ' + (Get-Content -LiteralPath $urlPath -Raw | ConvertFrom-Json).url)
        return
    }
    Start-Sleep -Seconds 1
}
throw 'Mobile access is still starting or failed. Check data/logs/mobile.stderr.log and mobile-tunnel.log.'
