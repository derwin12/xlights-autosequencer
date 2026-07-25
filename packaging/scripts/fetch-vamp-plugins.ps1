# Obtain and lay out Vamp plugin .dll files for Windows x86_64.
#
# Most Vamp plugin packs don't ship stable download URLs, so this verifies
# each expected .dll is present and prints instructions for any that are
# missing.
#
# Usage: .\packaging\scripts\fetch-vamp-plugins.ps1

$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
$Out = Join-Path $RepoRoot "packaging\pyinstaller\plugins\vamp\x86_64-windows"
New-Item -ItemType Directory -Force -Path $Out | Out-Null

# Expected plugin packs. ".dll" is the canonical Windows Vamp plugin
# extension. Names match what Python code requests via vamp.load_plugin()
# (see src/analyzer/algorithms/vamp_*.py).
$Expected = @(
    @{ Name = "qm-vamp-plugins.dll";      Url = "https://code.soundsoftware.ac.uk/projects/qm-vamp-plugins/" },
    @{ Name = "beatroot-vamp.dll";        Url = "https://code.soundsoftware.ac.uk/projects/beatroot-vamp" },
    @{ Name = "pyin.dll";                 Url = "https://code.soundsoftware.ac.uk/projects/pyin" },
    @{ Name = "nnls-chroma.dll";          Url = "https://code.soundsoftware.ac.uk/projects/nnls-chroma" },
    @{ Name = "silvet.dll";               Url = "https://code.soundsoftware.ac.uk/projects/silvet" },
    @{ Name = "bbc-vamp-plugins.dll";     Url = "https://code.soundsoftware.ac.uk/projects/bbc-vamp-plugins" },
    @{ Name = "segmentino.dll";           Url = "https://code.soundsoftware.ac.uk/projects/segmentino" },
    @{ Name = "tempogram.dll";            Url = "https://code.soundsoftware.ac.uk/projects/tempogram" },
    @{ Name = "vamp-aubio.dll";           Url = "https://aubio.org/vamp-aubio-plugins/" },
    @{ Name = "vamp-example-plugins.dll"; Url = "https://vamp-plugins.org/download.html" }
)

$Missing = $false
foreach ($entry in $Expected) {
    $path = Join-Path $Out $entry.Name
    if (Test-Path $path) {
        Write-Host "OK present: $path"
    } else {
        Write-Host "MISSING: $path"
        Write-Host "    source: $($entry.Url)"
        $Missing = $true
    }
}

if ($Missing) {
    Write-Host ""
    Write-Host "Action required: download the missing plugin packs from the URLs"
    Write-Host "listed above (Windows builds where the project publishes one),"
    Write-Host "unzip, and copy the .dll files into:"
    Write-Host "    $Out\"
    Write-Host ""
    Write-Host "Re-run this script after placing the files to confirm all packs"
    Write-Host "are present. Record SHA256 of each .dll in packaging\README.md."
    exit 1
}

Write-Host ""
Write-Host "All Vamp plugins present for x86_64-windows."
