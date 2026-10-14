$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:TEMP = Join-Path $PSScriptRoot 'data\tmp'
$env:TMP = $env:TEMP
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot 'data\cache\uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot '.tools\python'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
Set-Location $PSScriptRoot
if (!(Test-Path '.tools\bin\uv.exe')) {
    python -m pip install uv --target .tools --no-cache-dir
    if ($LASTEXITCODE) { throw 'Could not install uv' }
}
& .\.tools\bin\uv.exe sync
if ($LASTEXITCODE) { throw 'Could not install dependencies' }
if (!(Get-Command ffmpeg -ErrorAction SilentlyContinue)) { throw 'Install ffmpeg and add it to PATH' }
codex login status
Write-Host 'Use ChatGPT sign-in for Codex. Start the app with .\Start-Vault.ps1'
