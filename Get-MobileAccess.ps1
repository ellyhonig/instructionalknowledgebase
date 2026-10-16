$ErrorActionPreference = 'Stop'
$env:BJJVAULT_ROOT = $PSScriptRoot
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -X utf8 -m bjjvault.mobile_auth --link
if ($LASTEXITCODE) { throw 'Could not generate mobile sign-in link. Start-Vault.ps1 first.' }
