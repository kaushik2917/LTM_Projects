$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location (Join-Path $projectRoot 'frontend')
$nodeFolder = Join-Path $env:ProgramFiles 'nodejs'
if (Test-Path -LiteralPath $nodeFolder) { $env:Path = $nodeFolder + ';' + $env:Path }
& npm.cmd run dev -- --port 5173 --strictPort
