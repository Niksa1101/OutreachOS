# Fetches pinned BtbN FFmpeg GPL static builds into vendor/ffmpeg/.
# ADR-0007: GPL win64-gpl, never latest, SHA256-verified, source archived.
#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$ReleaseTag = "autobuild-2026-08-03-14-02"
$BaseUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/$ReleaseTag"

$WinZip = "ffmpeg-n7.1.5-12-g1fdbca85aa-win64-gpl-7.1.zip"
$WinZipSha256 = "5559c3a40827c273d9eb1a783b67d43aaa364bc1e907d558fab6cd7dd24f2d63"

$SourceTar = "ffmpeg-n7.1.5-12-g1fdbca85aa-linux64-gpl-7.1.tar.xz"
$SourceTarSha256 = "2164fd331d6578dc3c5b0becf9f86bf21d4fbb0424e2bb54240945203560b242"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VendorDir = Join-Path $RepoRoot "vendor\ffmpeg"
$SourceDir = Join-Path $VendorDir "source"
$StagingDir = Join-Path $env:TEMP "outreachos-ffmpeg-fetch"

function Assert-Sha256 {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected
    )
    $actual = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw "SHA256 mismatch for $Path`nExpected: $Expected`nActual:   $actual"
    }
}

New-Item -ItemType Directory -Force -Path $VendorDir | Out-Null
New-Item -ItemType Directory -Force -Path $SourceDir | Out-Null
if (Test-Path $StagingDir) { Remove-Item -Recurse -Force $StagingDir }
New-Item -ItemType Directory -Force -Path $StagingDir | Out-Null

$winPath = Join-Path $StagingDir $WinZip
Write-Host "Downloading $WinZip ..."
Invoke-WebRequest -Uri "$BaseUrl/$WinZip" -OutFile $winPath -UseBasicParsing
Assert-Sha256 -Path $winPath -Expected $WinZipSha256

$sourcePath = Join-Path $SourceDir $SourceTar
if (-not (Test-Path $sourcePath)) {
    Write-Host "Downloading source $SourceTar ..."
    Invoke-WebRequest -Uri "$BaseUrl/$SourceTar" -OutFile $sourcePath -UseBasicParsing
    Assert-Sha256 -Path $sourcePath -Expected $SourceTarSha256
}

Write-Host "Extracting ..."
Expand-Archive -Path $winPath -DestinationPath $StagingDir -Force

$extracted = Get-ChildItem -Path $StagingDir -Directory | Where-Object { $_.Name -like "ffmpeg-*" } | Select-Object -First 1
if ($null -eq $extracted) {
    throw "Could not find extracted ffmpeg directory under $StagingDir"
}

$binDir = Join-Path $extracted.FullName "bin"
foreach ($name in @("ffmpeg.exe", "ffprobe.exe")) {
    $src = Join-Path $binDir $name
    if (-not (Test-Path $src)) {
        throw "Missing $name in $binDir"
    }
    Copy-Item -Force $src (Join-Path $VendorDir $name)
}

$versionFile = Join-Path $VendorDir "VERSION.txt"
& (Join-Path $VendorDir "ffmpeg.exe") -version | Select-Object -First 1 | Set-Content -Path $versionFile -Encoding utf8

Write-Host "Pinned version written to $versionFile"
Write-Host "FFmpeg installed to $VendorDir"
Remove-Item -Recurse -Force $StagingDir
