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

Write-Host "-> Stamping packaging-manifest.json with build metadata"
& "$PSScriptRoot\generate-manifest.ps1"

Write-Host "-> Building app for target $Triple"
cargo tauri build --target $Triple
if ($LASTEXITCODE -ne 0) {
    Write-Error "error: cargo tauri build exited with code $LASTEXITCODE"
    exit $LASTEXITCODE
}

$BundleRoot = "src-tauri\target\$Triple\release\bundle"

# cargo tauri build's own "Finished 1 bundle at: ..." message has been
# observed to print successfully while this immediate Get-ChildItem check
# still comes back empty -- reproduced locally (2026-07-25, brief) and on a
# GitHub Actions runner (2026-07-26, still failing after a full 60s retry
# window). Root-caused on CI: Windows Defender's real-time scanning on the
# freshly-written ~220MB installer (GitHub-hosted Windows runners have it
# on by default) -- also explains why NSIS packaging itself took 6-7+
# minutes there vs under a minute locally. The real fix is excluding the
# workspace from Defender scanning in the workflow (see
# release-windows.yml); this retry loop is defense-in-depth only, not the
# primary fix -- don't just widen it further if this keeps happening.
$ExePath = $null
for ($i = 0; $i -lt 30 -and -not $ExePath; $i++) {
    if ($i -gt 0) { Start-Sleep -Seconds 2 }
    $ExePath = Join-Path $BundleRoot "nsis" | Get-ChildItem -Filter "*-setup.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
}

if (-not $ExePath) {
    # Write-Error under $ErrorActionPreference = "Stop" terminates the
    # script immediately -- diagnostics must run BEFORE it, not after
    # (a real bug in an earlier version of this check: the diagnostic
    # listing silently never ran because it came after Write-Error).
    Write-Host "-> Diagnostic listing of $BundleRoot (recursive):"
    Get-ChildItem -Recurse -Path $BundleRoot -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $($_.FullName)" }
    Write-Error "error: NSIS installer not produced under $BundleRoot\nsis\ after 60s of retrying"
    exit 1
}

Write-Host "Installer built: $($ExePath.FullName)"
Write-Host "Note: unsigned build -- Windows SmartScreen will show an 'unknown publisher' warning until an EV code-signing certificate is configured (packaging-manifest / tauri.conf.json > bundle.windows.certificateThumbprint)."
