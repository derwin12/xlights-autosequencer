# Run `cargo tauri build` for Windows x86_64 and locate the resulting
# installer. Basic v1: unsigned — Windows SmartScreen will warn on first
# run (no EV code-signing cert yet); see packaging/README.md for the
# signing follow-up once one is available.
#
# Usage: .\packaging\scripts\build-app.ps1

$ErrorActionPreference = "Stop"

$Triple = "x86_64-pc-windows-msvc"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location (Join-Path $RepoRoot "packaging\tauri")

Write-Host "-> Installing Tauri JS deps (if needed)"
pnpm install --frozen-lockfile

Write-Host "-> Building app for target $Triple"
cargo tauri build --target $Triple
if ($LASTEXITCODE -ne 0) {
    Write-Error "error: cargo tauri build exited with code $LASTEXITCODE"
    exit $LASTEXITCODE
}

$BundleRoot = "src-tauri\target\$Triple\release\bundle"
$ExePath = Join-Path $BundleRoot "nsis" | Get-ChildItem -Filter "*-setup.exe" -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $ExePath) {
    Write-Error "error: NSIS installer not produced under $BundleRoot\nsis\"
    exit 1
}

Write-Host "Installer built: $($ExePath.FullName)"
Write-Host "Note: unsigned build -- Windows SmartScreen will show an 'unknown publisher' warning until an EV code-signing certificate is configured (packaging-manifest / tauri.conf.json > bundle.windows.certificateThumbprint)."
