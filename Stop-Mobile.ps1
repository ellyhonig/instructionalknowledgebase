param([switch]$KeepEnabled)
$ErrorActionPreference = 'Stop'
$statePath = Join-Path $PSScriptRoot 'data\mobile-processes.json'
if (Test-Path -LiteralPath $statePath) {
    $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
    $running = Get-CimInstance Win32_Process -Filter "ProcessId=$($state.supervisor_pid)"
    if ($running -and $running.CommandLine -match 'bjjvault.mobile_access') {
        & taskkill.exe /PID $state.supervisor_pid /T /F | Out-Null
        if ($LASTEXITCODE) { throw 'Could not stop mobile access process tree.' }
    }
}
$resolvedRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$stateFiles = @('mobile-processes.json', 'mobile-url.json')
if (!$KeepEnabled) { $stateFiles += 'mobile-enabled' }
foreach ($name in $stateFiles) {
    $target = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ('data\' + $name)))
    if (!$target.StartsWith($resolvedRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected state file path' }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target }
}
Write-Host 'Mobile access stopped. Local ingestion continues.'
