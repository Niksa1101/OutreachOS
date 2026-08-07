# Build the Windows NSIS installer for OutreachOS.
#
# Produces a per-user installer under src-tauri/target/release/bundle/nsis/.
# The user's workspace (SQLite, outputs, caches) lives outside the install
# directory in a folder they choose at first run; uninstall removes only the
# application under LocalAppData\Programs.
#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "==> Ensuring placeholder icons exist"
node (Join-Path $RepoRoot "scripts\gen-placeholder-icon.mjs")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Fetching pinned FFmpeg binaries"
& (Join-Path $RepoRoot "scripts\fetch-ffmpeg.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Building frontend"
Push-Location $RepoRoot
try {
    pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    pnpm run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

Write-Host "==> Freezing backend sidecar"
& (Join-Path $RepoRoot "scripts\build-backend.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Staging Tauri bundle resources"
& (Join-Path $RepoRoot "scripts\stage-bundle-resources.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Building Tauri NSIS installer"
Push-Location $RepoRoot
try {
    pnpm tauri build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

$BundleDir = Join-Path $RepoRoot "src-tauri\target\release\bundle\nsis"
Write-Host ""
Write-Host "Installer build complete."
if (Test-Path $BundleDir) {
    Get-ChildItem -Path $BundleDir -Filter "*.exe" | ForEach-Object {
        Write-Host "  $($_.FullName)"
    }
}
