# Stamp packaging/tauri/src-tauri/packaging-manifest.json with real build
# metadata before packaging. The checked-in file is a static placeholder
# ("0.0.0-dev") -- without this step every build (including tagged CI
# releases) ships that placeholder as its displayed version, since nothing
# else ever rewrites it.
#
# Version derivation:
#   - Exactly on a git tag (CI release builds, tags/v*)  -> the tag, "v" stripped
#   - Otherwise (local/dev builds)                        -> tauri.conf.json's
#     base version + the short commit sha (dirty-suffixed if uncommitted
#     changes exist), e.g. "0.1.0+a1b2c3d" or "0.1.0+a1b2c3d-dirty"
#
# Usage: .\packaging\scripts\generate-manifest.ps1

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $RepoRoot

$TauriConf = Get-Content "packaging\tauri\src-tauri\tauri.conf.json" -Raw | ConvertFrom-Json
$BaseVersion = $TauriConf.version

$ShortSha = (git rev-parse --short HEAD).Trim()
$Dirty = if (git status --porcelain --untracked-files=no) { "-dirty" } else { "" }

# `git describe --exact-match` exits non-zero (128) when HEAD isn't exactly
# on a tag -- the common case for local/dev builds, not an error condition
# here. Check $LASTEXITCODE explicitly rather than try/catch: a non-zero
# exit from a *native* command doesn't throw a terminating exception even
# under $ErrorActionPreference = "Stop", so try/catch wouldn't reset it
# anyway -- it would just leave $LASTEXITCODE non-zero, which becomes this
# whole script's own exit code and silently fails the CI build step even
# though the manifest was written correctly.
$ExactTag = git describe --tags --exact-match HEAD 2>$null
if ($LASTEXITCODE -ne 0) {
    $ExactTag = $null
}
$global:LASTEXITCODE = 0

if ($ExactTag) {
    $AppVersion = $ExactTag.Trim().TrimStart("v")
} else {
    $AppVersion = "$BaseVersion+$ShortSha$Dirty"
}

$Manifest = [ordered]@{
    app_version                 = $AppVersion
    build_timestamp              = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    target_arch                  = "x86_64"
    frontend_commit               = $ShortSha
    backend_commit                = $ShortSha
    bundled_vamp_plugins          = @()
    download_model_manifest_url  = "src/packaging/model_manifest.json"
}

$ManifestPath = "packaging\tauri\src-tauri\packaging-manifest.json"
($Manifest | ConvertTo-Json) | Set-Content -Path $ManifestPath -NoNewline
Write-Host "-> Stamped $ManifestPath (app_version=$AppVersion)"
