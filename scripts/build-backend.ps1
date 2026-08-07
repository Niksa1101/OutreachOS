#Requires -Version 5.1
<#
.SYNOPSIS
  Freeze the FastAPI backend with PyInstaller (ADR-0006: onedir).

.DESCRIPTION
  Produces ``backend/dist/outreachos-backend/`` with ``outreachos-backend.exe``,
  ``outreachos-render.exe``, and ``_internal/``. Stage with
  ``scripts/stage-bundle-resources.ps1`` before ``pnpm tauri build``.

  FFmpeg is **not** embedded here — Tauri bundles ``vendor/ffmpeg/`` separately
  (ADR-0004).
#>
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $RepoRoot "backend"
$DistDir = Join-Path (Join-Path $BackendDir "dist") "outreachos-backend"
$FfmpegDir = Join-Path $RepoRoot "vendor\ffmpeg"

if (-not (Test-Path (Join-Path $FfmpegDir "ffmpeg.exe"))) {
    Write-Host "Fetching pinned FFmpeg ..."
    & (Join-Path $RepoRoot "scripts\fetch-ffmpeg.ps1")
}

Write-Host "Building backend sidecar with PyInstaller ..."
Push-Location $BackendDir
try {
    uv sync --group dev
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    uv run pyinstaller outreachos-backend.spec --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "Running frozen sidecar smoke tests ..."
    uv run pytest tests/test_frozen_sidecar.py -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

$ExePath = Join-Path $DistDir "outreachos-backend.exe"
$RenderExePath = Join-Path $DistDir "outreachos-render.exe"
$VersionsDir = Join-Path $DistDir "_internal\alembic\versions"

if (-not (Test-Path $ExePath)) {
    throw "PyInstaller did not produce $ExePath"
}
if (-not (Test-Path $RenderExePath)) {
    throw "PyInstaller did not produce $RenderExePath"
}
if (-not (Test-Path $VersionsDir)) {
    throw "Alembic versions/ were not bundled - migrations would no-op silently"
}

Write-Host "Backend sidecar built at $DistDir"
