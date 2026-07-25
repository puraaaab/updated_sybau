param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("start", "stop", "restart")]
    [string]$Action
)

$ErrorActionPreference = "Continue"
$ProjectRoot = $PSScriptRoot

# Path to the project's virtual environment Python executable
$VenvPython = "$ProjectRoot\.venv\Scripts\python.exe"

function Stop-VMS {
    Write-Host "Stopping Sybau VMS Services..." -ForegroundColor Yellow

    # 1. Stop Docker
    Write-Host "  Stopping Docker containers..."
    Set-Location $ProjectRoot
    & docker-compose down 2>&1 | ForEach-Object { if ($_ -notmatch 'level=warning') { Write-Host $_ } }

    # 2. Kill Uvicorn (Backend)
    Write-Host "  Stopping Python backend (uvicorn)..."
    $pythonProcs = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -and $_.CommandLine -match 'uvicorn'
    }
    foreach ($proc in $pythonProcs) {
        Write-Host "    Killing Backend PID: $($proc.ProcessId)"
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }

    # 2b. Kill NVR Emulator and orphaned FFmpeg streams
    Write-Host "  Stopping NVR Emulator..."
    $emulatorProcs = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -and $_.CommandLine -match 'nvr_emulator'
    }
    foreach ($proc in $emulatorProcs) {
        Write-Host "    Killing Emulator PID: $($proc.ProcessId)"
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Get-Process -Name "ffmpeg" -ErrorAction SilentlyContinue | Stop-Process -Force

    # 3. Kill Vite (Frontend)
    Write-Host "  Stopping Node frontend (vite)..."
    $nodeProcs = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'node.exe' -and $_.CommandLine -match 'vite'
    }
    foreach ($proc in $nodeProcs) {
        Write-Host "    Killing Frontend PID: $($proc.ProcessId)"
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }

    Write-Host "All VMS Services Stopped." -ForegroundColor Green
}

function Start-VMS {
    Write-Host "Starting Sybau VMS Services..." -ForegroundColor Cyan

    # 1. Start Docker (PostgreSQL, Qdrant, Kafka)
    Write-Host "  Starting Docker containers..."
    Set-Location $ProjectRoot
    & docker-compose up -d 2>&1 | ForEach-Object { if ($_ -notmatch 'level=warning') { Write-Host $_ } }
    Write-Host "  Waiting for services to be ready..."
    Start-Sleep -Seconds 5

    # 2. Seed RTSP Cameras
    Write-Host "  Seeding RTSP Cameras in Database..."
    & $VenvPython .\backend\scripts\seed_rtsp_cams.py

    # Create logs directory
    $LogsDir = "$ProjectRoot\logs"
    if (-not (Test-Path $LogsDir)) { New-Item -ItemType Directory -Path $LogsDir | Out-Null }

    # 3. Start Backend — stdout+stderr merged into backend.log via cmd.exe redirection (prevents PowerShell stderr wrapping)
    Write-Host "  Starting Backend server (uvicorn + venv)... (Logging to logs\backend.log)"
    $bCmd = "/c cd /d `"$ProjectRoot`" && `"$VenvPython`" -u -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 > `"$LogsDir\backend.log`" 2>&1"
    Start-Process cmd.exe -ArgumentList $bCmd -WindowStyle Hidden

    # 4. Start Frontend — stdout+stderr merged into frontend.log
    Write-Host "  Starting Frontend server (Vite)... (Logging to logs\frontend.log)"
    $fCmd = "/c cd /d `"$ProjectRoot\frontend`" && npm run dev > `"$LogsDir\frontend.log`" 2>&1"
    Start-Process cmd.exe -ArgumentList $fCmd -WindowStyle Hidden

    # 5. Start NVR Emulator — stdout+stderr (incl. all FFmpeg camera output) merged into nvr.log
    Write-Host "  Starting NVR Emulator (FFmpeg stream loop)... (Logging to logs\nvr.log)"
    $nCmd = "/c cd /d `"$ProjectRoot`" && `"$VenvPython`" -u backend\scripts\nvr_emulator.py > `"$LogsDir\nvr.log`" 2>&1"
    Start-Process cmd.exe -ArgumentList $nCmd -WindowStyle Hidden

    # 6. Wait for backend to be ready — polls /docs up to 120s
    Write-Host "  Waiting for backend to respond..."
    $backendReady = $false
    $attempts = 0
    while (-not $backendReady -and $attempts -lt 60) {
        Start-Sleep -Seconds 2
        $attempts++
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/docs" -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop
            if ($r.StatusCode -eq 200) { $backendReady = $true }
        } catch { }
        if ($attempts % 5 -eq 0) { Write-Host "    Still waiting for response... ($($attempts * 2)s elapsed)" }
    }
    if ($backendReady) {
        Write-Host "  Backend ready! ($($attempts * 2)s)" -ForegroundColor Green
    } else {
        Write-Host "  WARNING: Backend did not respond in 120s - check logs\backend.log" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "All VMS Services Started!" -ForegroundColor Green
    Write-Host "  Frontend : http://localhost:5173" -ForegroundColor Cyan
    Write-Host "  Backend  : http://localhost:8000" -ForegroundColor Cyan
    Write-Host "  API Docs : http://localhost:8000/docs" -ForegroundColor Cyan
}

switch ($Action) {
    "stop"    { Stop-VMS }
    "start"   { Start-VMS }
    "restart" { Stop-VMS; Start-VMS }
}
