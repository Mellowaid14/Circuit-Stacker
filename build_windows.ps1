$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonExe = $venvPython
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
}
else {
    throw "No usable Python launcher was found. Use the project's .venv or install Python with the 'py' launcher."
}

if ($pythonExe -eq "py") {
    py -m pip install -e .[build]
    py -m PyInstaller --clean --noconfirm .\circuit_stackers.spec
}
else {
    & $pythonExe -m pip install -e .[build]
    & $pythonExe -m PyInstaller --clean --noconfirm .\circuit_stackers.spec
}

Write-Host ""
Write-Host "Build complete."
Write-Host "Share this folder:"
Write-Host "  $projectRoot\dist\CircuitStackers"
