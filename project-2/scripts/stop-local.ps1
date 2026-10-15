$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$pidFile = Join-Path $projectRoot '.runtime/server-processes.json'
if (!(Test-Path -LiteralPath $pidFile)) { Write-Host 'No recorded project servers.'; exit 0 }
$record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
foreach ($name in @('backend','frontend')) {
    $recordedId = [int]$record.$name
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $recordedId" -ErrorAction SilentlyContinue
    if (!$processInfo) { continue }
    $expected = if ($name -eq 'backend') { 'uvicorn app.main:app' } else { 'vite' }
    if ($processInfo.CommandLine -notlike "*$expected*") { Write-Warning "PID $recordedId no longer matches the recorded $name server; leaving it running."; continue }
    Stop-Process -Id $recordedId
    Write-Host "Stopped project $name process $recordedId."
}
