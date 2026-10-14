$ErrorActionPreference = 'Stop'
$env:BJJVAULT_ROOT = $PSScriptRoot
$env:PYTHONUTF8 = '1'
$env:TEMP = Join-Path $PSScriptRoot 'data\tmp'
$env:TMP = $env:TEMP
$env:HF_HOME = Join-Path $PSScriptRoot 'data\cache\huggingface'
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot 'data\cache\uv'
New-Item -ItemType Directory -Force -Path $env:TEMP, (Join-Path $PSScriptRoot 'data\logs') | Out-Null
if (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host 'A server is already listening at http://localhost:8765'
    exit
}
$process = Start-Process -FilePath (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -ArgumentList '-X utf8 -m bjjvault.cli serve' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'data\logs\server.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'data\logs\server.stderr.log')
$process.Id | Set-Content (Join-Path $PSScriptRoot 'data\server.pid')
Write-Host 'BJJ Vault started at http://localhost:8765. Closing this shell does not stop it.'
