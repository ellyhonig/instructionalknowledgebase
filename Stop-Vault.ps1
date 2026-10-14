$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'data\mobile-processes.json')) {
    & (Join-Path $PSScriptRoot 'Stop-Mobile.ps1') -KeepEnabled
}
$listeners = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
    if ($process.CommandLine -match 'bjjvault.cli serve') {
        Stop-Process -Id $process.ProcessId
        Write-Host 'BJJ Vault stopped. Start-Vault.ps1 resumes unfinished jobs.'
    }
}
