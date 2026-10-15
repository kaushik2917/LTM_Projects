$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
$nodeFolder = Join-Path $env:ProgramFiles 'nodejs'
if (Test-Path -LiteralPath $nodeFolder) { $env:Path = $nodeFolder + ';' + $env:Path }
if (!(Test-Path -LiteralPath 'backend/.venv/Scripts/python.exe')) {
    & py -3 -m venv backend/.venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
}
& 'backend/.venv/Scripts/python.exe' -m pip install -r backend/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
& npm.cmd ci --prefix frontend
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed. Node 20.19+ or 22.12+ is required.' }
Write-Host 'Ready. Run scripts/start-backend.ps1 and scripts/start-frontend.ps1 in separate terminals.'
