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

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    $commonPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $commonPaths) {
        if (Test-Path $candidate) {
            $iscc = @{ Source = $candidate }
            break
        }
    }
}

if (-not $iscc) {
    throw "Inno Setup Compiler (ISCC.exe) was not found. Install Inno Setup 6 or add ISCC to PATH."
}

& $iscc.Source ".\CircuitStackerInstaller.iss"

Write-Host ""
Write-Host "Installer build complete."
Write-Host "Share this file:"
$installer = Get-ChildItem -Path (Join-Path $projectRoot "output") -Filter "CircuitStackerSetup-*.exe" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($installer) {
    Write-Host "  $($installer.FullName)"
}
else {
    Write-Host "  $projectRoot\output\CircuitStackerSetup-<version>.exe"
}
