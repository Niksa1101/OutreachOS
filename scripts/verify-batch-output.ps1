# Validate exported or staged MP4 outputs against the PRD §6.1 render contract.
#
# Usage:
#   .\scripts\verify-batch-output.ps1 -InputDir C:\export\batch -ExpectedDurationSec 25
#   .\scripts\verify-batch-output.ps1 -InputDir .\out -ReportFile .\report.json
#Requires -Version 5.1
param(
    [Parameter(Mandatory)][string]$InputDir,
    [double]$ExpectedDurationSec = 0,
    [double]$DurationToleranceSec = 0.15,
    [string]$ReportFile = "",
    [string]$FfprobePath = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $FfprobePath) {
    $FfprobePath = Join-Path $RepoRoot "vendor\ffmpeg\ffprobe.exe"
}

if (-not (Test-Path $FfprobePath)) {
    throw "ffprobe not found at $FfprobePath - run scripts/fetch-ffmpeg.ps1"
}
if (-not (Test-Path $InputDir)) {
    throw "Input directory not found: $InputDir"
}

function Get-MediaInfo {
    param([string]$Path)
    $json = & $FfprobePath `
        -v quiet `
        -print_format json `
        -show_format `
        -show_streams `
        $Path 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "ffprobe failed for $Path`: $json"
    }
    return $json | ConvertFrom-Json
}

$files = @(Get-ChildItem -Path $InputDir -Filter "*.mp4" -File | Sort-Object Name)
if ($files.Count -eq 0) {
    throw "No MP4 files found in $InputDir"
}

$results = @()
$failures = 0

foreach ($file in $files) {
    $info = Get-MediaInfo -Path $file.FullName
    $video = @($info.streams | Where-Object { $_.codec_type -eq "video" })[0]
    $audio = @($info.streams | Where-Object { $_.codec_type -eq "audio" })[0]
    $issues = @()

    if (-not $video) {
        $issues += "missing video stream"
    }
    else {
        if ([int]$video.width -ne 1920) { $issues += "width=$($video.width), expected 1920" }
        if ([int]$video.height -ne 1080) { $issues += "height=$($video.height), expected 1080" }
        if ($video.codec_name -ne "h264") { $issues += "video codec=$($video.codec_name), expected h264" }

        $fps = $null
        if ($video.avg_frame_rate -and $video.avg_frame_rate -match "^(\d+)/(\d+)$") {
            $num = [double]$Matches[1]
            $den = [double]$Matches[2]
            if ($den -gt 0) { $fps = $num / $den }
        }
        if ($null -eq $fps -or [math]::Abs($fps - 30.0) -gt 0.05) {
            $issues += "fps=$fps, expected ~30"
        }
    }

    if (-not $audio) {
        $issues += "missing audio stream"
    }
    elseif ($audio.codec_name -ne "aac") {
        $issues += "audio codec=$($audio.codec_name), expected aac"
    }

    $duration = [double]$info.format.duration
    if ($ExpectedDurationSec -gt 0) {
        $delta = [math]::Abs($duration - $ExpectedDurationSec)
        if ($delta -gt $DurationToleranceSec) {
            $issues += ("duration={0:N3}s, expected {1:N3}s (tolerance {2:N3}s)" -f $duration, $ExpectedDurationSec, $DurationToleranceSec)
        }
    }

    $passed = ($issues.Count -eq 0)
    if (-not $passed) { $failures++ }

    $entry = [ordered]@{
        file     = $file.Name
        passed   = $passed
        duration = $duration
        width    = if ($video) { [int]$video.width } else { $null }
        height   = if ($video) { [int]$video.height } else { $null }
        issues   = @($issues)
    }
    $results += $entry

    $status = if ($passed) { "PASS" } else { "FAIL" }
    $detail = if ($passed) { "" } else { " - $($issues -join '; ')" }
    Write-Host "$status  $($file.Name)$detail"
}

Write-Host ""
Write-Host "Checked $($files.Count) file(s): $($files.Count - $failures) passed, $failures failed."

$report = [ordered]@{
    checked_at           = (Get-Date -Format "o")
    input_dir            = (Resolve-Path $InputDir).Path
    expected_duration_sec = $ExpectedDurationSec
    total                = $files.Count
    passed               = $files.Count - $failures
    failed               = $failures
    files                = $results
}

if ($ReportFile) {
    $report | ConvertTo-Json -Depth 6 | Set-Content -Path $ReportFile -Encoding UTF8
    Write-Host "Report written to $ReportFile"
}

if ($failures -gt 0) {
    exit 1
}
