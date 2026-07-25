# Build the PyInstaller backend onedir sidecar for Windows x86_64.
#
# Usage: .\packaging\scripts\build-backend.ps1
#
# Produces: packaging\tauri\src-tauri\binaries\backend-x86_64-pc-windows-msvc\
#   (Tauri's resources mechanism expects this exact directory name — see
#   tauri.conf.json > bundle.resources — with the exe inside renamed to match.)
#
# Windows only ships one practical arch target (x86_64) for now — no ARM64
# Vamp plugin builds are known to exist, so this script doesn't take an
# arch argument.

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $RepoRoot

$Triple = "x86_64-pc-windows-msvc"
$VenvDir = ".build-venv-$Triple"
$WorkDir = ".build-pyinstaller\$Triple"
$DistDir = "packaging\tauri\src-tauri\binaries"

# Require Python 3.11 specifically (madmom has no 3.12+ wheels; torch CPU
# wheel availability was still sparse for 3.13/3.14 at time of writing).
$Py311 = if ($env:PY311) { $env:PY311 } else { "py" }
$PyArgs = if ($env:PY311) { @() } else { @("-3.11") }

$VersionOutput = & $Py311 @PyArgs --version 2>&1
if ($VersionOutput -notmatch "Python 3\.11\.") {
    Write-Error "error: '$Py311 $PyArgs' reports '$VersionOutput' — expected Python 3.11.x. Install from python.org or set `$env:PY311 to a full path."
    exit 2
}
Write-Host "-> Using $Py311 $PyArgs ($VersionOutput)"

Write-Host "-> Preparing venv at $VenvDir"
& $Py311 @PyArgs -m venv $VenvDir
$VenvPython = "$VenvDir\Scripts\python.exe"

Write-Host "-> Installing backend dependencies"
& $VenvPython -m pip install --upgrade pip wheel
# setuptools>=81 removed the bundled pkg_resources compatibility shim;
# madmom's __init__.py does a hard `import pkg_resources`, so the latest
# setuptools silently breaks it (ModuleNotFoundError at madmom import time,
# not at pip-install time). Pin below that removal.
& $VenvPython -m pip install "setuptools<81"
& $VenvPython -m pip install -e ".[stems,lyrics]"
& $VenvPython -m pip install "pyinstaller>=6,<7"

# madmom builds Cython extensions at install time; pre-install build deps
# outside the implicit PEP 517 isolated env (same rationale as build-backend.sh).
& $VenvPython -m pip install --upgrade "cython>=3" "numpy<2"

# madmom/vamp are optional on Windows too — don't fail the build if they
# refuse to install (madmom in particular has spotty Windows wheel/source
# support; vamp's Python bindings need the Vamp SDK headers on PATH).
& $VenvPython -m pip install "madmom>=0.16" --no-build-isolation
if ($LASTEXITCODE -ne 0) {
    Write-Warning "madmom install failed — beats-only analysis will be unavailable in the bundle"
}
& $VenvPython -m pip install "vamp>=1.1"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "vamp install failed — vamp plugins will be unavailable in the bundle"
}

New-Item -ItemType Directory -Force -Path $DistDir, $WorkDir | Out-Null

Write-Host "-> Running PyInstaller"
& $VenvPython -m PyInstaller packaging\pyinstaller\backend.spec `
    --distpath $DistDir --workpath $WorkDir --clean --noconfirm

# PyInstaller onedir outputs <distpath>\backend\ containing backend.exe.
# Rename the folder and the exe inside to the target-triple-suffixed name
# Tauri's resources config and main.rs::backend_binary_path expect.
$FinalDir = "$DistDir\backend-$Triple"
if (Test-Path $FinalDir) {
    Remove-Item -Recurse -Force $FinalDir
}
Rename-Item "$DistDir\backend" "backend-$Triple"

Rename-Item "$FinalDir\backend.exe" "backend-$Triple.exe"

Write-Host "-> Running self-test against bundled executable"
& "$FinalDir\backend-$Triple.exe" --self-test

Write-Host "Backend built: $FinalDir\"
