# Stage the sidecar onedir and FFmpeg binaries for Tauri bundling.
#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDist = Join-Path $RepoRoot "backend\dist\outreachos-backend"
$VendorFfmpeg = Join-Path $RepoRoot "vendor\ffmpeg"
$StageRoot = Join-Path $RepoRoot "src-tauri\bundle-resources"
$StageBackend = Join-Path $StageRoot "backend"
$StageFfmpeg = Join-Path $StageRoot "ffmpeg"
$Licenses = Join-Path $RepoRoot "THIRD-PARTY-LICENSES.md"

if (-not (Test-Path (Join-Path $BackendDist "outreachos-backend.exe"))) {
    throw "Missing $BackendDist\outreachos-backend.exe - run scripts/build-backend.ps1 first"
}
if (-not (Test-Path (Join-Path $BackendDist "outreachos-render.exe"))) {
    throw "Missing $BackendDist\outreachos-render.exe - run scripts/build-backend.ps1 first"
}

foreach ($name in @("ffmpeg.exe", "ffprobe.exe")) {
    $path = Join-Path $VendorFfmpeg $name
    if (-not (Test-Path $path)) {
        throw "Missing $path - run scripts/fetch-ffmpeg.ps1 first"
    }
}

Write-Host "Staging bundle resources under $StageRoot ..."

if (Test-Path $StageRoot) {
    Get-ChildItem -Path $StageRoot -Force | Where-Object { $_.Name -ne ".gitkeep" } | Remove-Item -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $StageBackend, $StageFfmpeg | Out-Null

Copy-Item -Path (Join-Path $BackendDist "*") -Destination $StageBackend -Recurse -Force
Copy-Item -Path (Join-Path $VendorFfmpeg "ffmpeg.exe") -Destination $StageFfmpeg -Force
Copy-Item -Path (Join-Path $VendorFfmpeg "ffprobe.exe") -Destination $StageFfmpeg -Force
$VersionFile = Join-Path $VendorFfmpeg "VERSION.txt"
if (Test-Path $VersionFile) {
    Copy-Item -Path $VersionFile -Destination $StageFfmpeg -Force
}
if (Test-Path $Licenses) {
    Copy-Item -Path $Licenses -Destination $StageRoot -Force
}

Write-Host "Staged backend -> $StageBackend"
Write-Host "Staged ffmpeg  -> $StageFfmpeg"
if (Test-Path $Licenses) {
    Write-Host "Staged licenses -> $StageRoot\THIRD-PARTY-LICENSES.md"
}
