$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location (Join-Path $projectRoot 'backend')
$python = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run scripts/setup.ps1 first to create the Python environment.' }
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --ws-max-size 32768
