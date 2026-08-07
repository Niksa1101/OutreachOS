# Monitor OutreachOS processes for outbound network connections during P6 acceptance.
#
# Allows loopback (127.0.0.1, ::1) — Tauri ↔ sidecar traffic is expected.
# Flags any other remote TCP endpoint as a violation of PRD §2 principle 7.
#
# Usage:
#   .\scripts\verify-no-network.ps1 -LogFile .\p6-network-log.txt
#
# Stop with Ctrl+C when the acceptance session ends, then review the log.
#Requires -Version 5.1
param(
    [string]$LogFile = "",
    [int]$IntervalSec = 2
)

$ErrorActionPreference = "Stop"

$ProcessNames = @("outreachos", "outreachos-backend")
$Loopback = @("127.0.0.1", "::1", "0.0.0.0")

function Test-LoopbackAddress {
    param([string]$Address)
    if ($Loopback -contains $Address) { return $true }
    if ($Address -eq "" -or $Address -eq $null) { return $true }
    return $false
}

function Write-Log {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Write-Host $line
    if ($LogFile) {
        Add-Content -Path $LogFile -Value $line -Encoding UTF8
    }
}

if ($LogFile) {
    $dir = Split-Path -Parent $LogFile
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    Set-Content -Path $LogFile -Value "# OutreachOS network monitor started $(Get-Date -Format o)" -Encoding UTF8
}

Write-Log "Monitoring processes: $($ProcessNames -join ', ')"
Write-Log "Allowed addresses: loopback only. Interval: ${IntervalSec}s"
Write-Log "Press Ctrl+C to stop."

$seenViolations = @{}

try {
    while ($true) {
        $pids = @()
        foreach ($name in $ProcessNames) {
            $pids += @(Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object { $_.Id })
        }
        $pids = $pids | Select-Object -Unique

        if ($pids.Count -eq 0) {
            Start-Sleep -Seconds $IntervalSec
            continue
        }

        foreach ($procId in $pids) {
            $connections = Get-NetTCPConnection -OwningProcess $procId -ErrorAction SilentlyContinue |
                Where-Object { $_.State -eq "Established" -or $_.State -eq "SynSent" }

            foreach ($conn in $connections) {
                $remote = $conn.RemoteAddress
                if (Test-LoopbackAddress -Address $remote) { continue }

                $key = "$procId|$($conn.LocalAddress):$($conn.LocalPort)->$remote`:$($conn.RemotePort)"
                if ($seenViolations.ContainsKey($key)) { continue }
                $seenViolations[$key] = $true

                $procName = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName
                Write-Log "VIOLATION: $procName (PID $procId) -> $remote`:$($conn.RemotePort) [$($conn.State)]"
            }
        }

        Start-Sleep -Seconds $IntervalSec
    }
}
finally {
    $count = $seenViolations.Count
    if ($count -eq 0) {
        Write-Log "Monitor stopped. Zero network violations detected."
    }
    else {
        Write-Log "Monitor stopped. $count unique non-loopback connection(s) detected."
        exit 1
    }
}
