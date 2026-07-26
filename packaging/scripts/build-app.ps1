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

# Capture cargo tauri build's own output while still streaming it live --
# its "Finished N bundle(s) at: <path>" line is tauri-cli's own
# already-verified confirmation that the file exists (it wouldn't print
# that line otherwise). Parsing the path directly from that line, rather
# than independently re-discovering it via a fresh Get-ChildItem
# enumeration afterward, sidesteps a real bug found 2026-07-26: on
# GitHub-hosted Windows runners, that independent re-check still failed
# to find the file even a full 60 real seconds after this success message
# printed (an Add-MpPreference Defender exclusion, added as a first
# attempt at a fix, made no measurable difference -- GitHub-hosted
# windows-latest runners have Tamper Protection enabled by default, which
# is documented to silently no-op that cmdlet). Trusting cargo tauri
# build's own report instead of re-deriving it is the actual fix, not a
# longer retry window.
$OutputLines = @()
cargo tauri build --target $Triple 2>&1 | ForEach-Object {
    Write-Host $_
    $OutputLines += "$_"
}
if ($LASTEXITCODE -ne 0) {
    Write-Error "error: cargo tauri build exited with code $LASTEXITCODE"
    exit $LASTEXITCODE
}

$ExePath = $null
for ($i = 0; $i -lt $OutputLines.Count; $i++) {
    if ($OutputLines[$i] -match "Finished \d+ bundle") {
        $candidate = $OutputLines[$i + 1].Trim()
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            $ExePath = Get-Item -LiteralPath $candidate
        }
        break
    }
}

if (-not $ExePath) {
    Write-Error "error: could not find a 'Finished N bundle(s) at: <path>' line in cargo tauri build's output, or the reported path doesn't exist"
    exit 1
}

Write-Host "Installer built: $($ExePath.FullName)"
Write-Host "Note: unsigned build -- Windows SmartScreen will show an 'unknown publisher' warning until an EV code-signing certificate is configured (packaging-manifest / tauri.conf.json > bundle.windows.certificateThumbprint)."
