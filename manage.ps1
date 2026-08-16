param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("start", "stop", "restart")]
    [string]$Action
)

$ErrorActionPreference = "Continue"
$ProjectRoot = $PSScriptRoot

# Path to Python executable (virtualenv or system python fallback)
$VenvPython = "$ProjectRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    $foundPython = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($foundPython) {
        $VenvPython = $foundPython
    } else {
        $VenvPython = "python"
    }
}


function Test-DockerAvailable {
    try {
        $p = Start-Process -FilePath "cmd.exe" -ArgumentList "/c docker info >nul 2>&1" -WindowStyle Hidden -PassThru
        if (-not $p.WaitForExit(8000)) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            return $false
        }
        return ($p.ExitCode -eq 0)
    } catch {
        return $false
    }
}

function Stop-VMS {
    Write-Host "Stopping Sybau VMS Services..." -ForegroundColor Yellow

    # 1. Stop Docker (if daemon is responding)
    if (Test-DockerAvailable) {
        Write-Host "  Stopping Docker containers..."
        Set-Location $ProjectRoot
        cmd.exe /c "docker compose down --remove-orphans"
    } else {
        Write-Host "  Docker daemon unresponsive or stopped - skipping container teardown." -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 1

    # 2. Kill Uvicorn (Backend)
    Write-Host "  Stopping Python backend (uvicorn)..."
    $pythonProcs = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -and ($_.CommandLine -match 'uvicorn' -or $_.CommandLine -match 'backend.main')
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

    # 1. Create required directories
    $LogsDir = "$ProjectRoot\logs"
    if (-not (Test-Path $LogsDir)) {
        New-Item -ItemType Directory -Path $LogsDir | Out-Null
    }

    $StorageDirs = @(
        "$ProjectRoot\storage\recordings",
        "$ProjectRoot\storage\snapshots",
        "$ProjectRoot\storage\exports",
        "$ProjectRoot\storage\temp"
    )
    foreach ($dir in $StorageDirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
    }

    # 2. Start Docker Infrastructure if available
    if (Test-DockerAvailable) {
        Write-Host "  Starting Docker infrastructure containers..."
        Set-Location $ProjectRoot
        cmd.exe /c "docker compose up -d postgres qdrant mediamtx minio zookeeper kafka"
        Write-Host "  Waiting for infrastructure services to initialize..."
        Start-Sleep -Seconds 3
    } else {
        Write-Host "  Docker Desktop daemon not responding - system using local fallback database." -ForegroundColor Yellow
    }

    # 3. Seed RTSP Cameras in Database
    Write-Host "  Seeding RTSP Cameras in Database..."
    & $VenvPython .\backend\scripts\seed_rtsp_cams.py

    # 4. Start Backend (uvicorn)
    Write-Host "  Starting Backend server (uvicorn + venv)... (Logging to logs\backend.log)"
    # Load .env so VMS_SECRET_KEY and other vars are available to uvicorn.
    # Without this every restart generates a new ephemeral JWT key, invalidating all browser sessions.
    $envFile = "$ProjectRoot\.env"
    $envArg = ""
    if (Test-Path $envFile) {
        $envArg = "--env-file `".env`""
    }
    $bCmd = "/c cd /d `"$ProjectRoot`" && `"$VenvPython`" -u -m uvicorn backend.main:app --host 0.0.0.0 --port 7000 --no-access-log $envArg > `"$LogsDir\backend.log`" 2>&1"
    Start-Process cmd.exe -ArgumentList $bCmd -WindowStyle Hidden


    # 5. Start Frontend (Vite)
    Write-Host "  Starting Frontend server (Vite)... (Logging to logs\frontend.log)"
    $fCmd = "/c cd /d `"$ProjectRoot\frontend`" && npm run dev > `"$LogsDir\frontend.log`" 2>&1"
    Start-Process cmd.exe -ArgumentList $fCmd -WindowStyle Hidden

    # 6. Start NVR Emulator (FFmpeg stream loop)
    Write-Host "  Starting NVR Emulator (FFmpeg stream loop)... (Logging to logs\nvr.log)"
    $nCmd = "/c cd /d `"$ProjectRoot`" && `"$VenvPython`" -u backend\scripts\nvr_emulator.py > `"$LogsDir\nvr.log`" 2>&1"
    Start-Process cmd.exe -ArgumentList $nCmd -WindowStyle Hidden

    # 7. Wait for backend to be ready
    Write-Host "  Waiting for backend to respond..."
    $backendReady = $false
    $attempts = 0
    while (-not $backendReady -and $attempts -lt 80) {
        Start-Sleep -Milliseconds 500
        $attempts++
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect("127.0.0.1", 7000)
            if ($tcp.Connected) {
                $backendReady = $true
                $tcp.Close()
            }
        } catch {
            # Backend starting up
        }
        if ($attempts % 10 -eq 0) {
            Write-Host "    Backend initialization progress... ($($attempts / 2)s elapsed)"
        }
    }
    if ($backendReady) {
        Write-Host "  Backend ready! ($($attempts * 2)s)" -ForegroundColor Green
    } else {
        Write-Host "  WARNING: Backend did not respond in 80s - check logs\backend.log" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "All VMS Services Started!" -ForegroundColor Green
    Write-Host "  Frontend : http://localhost:5173" -ForegroundColor Cyan
    Write-Host "  Backend  : http://localhost:7000" -ForegroundColor Cyan
    Write-Host "  API Docs : http://localhost:7000/docs" -ForegroundColor Cyan

}

switch ($Action) {
    "stop"    { Stop-VMS }
    "start"   { Start-VMS }
    "restart" { Stop-VMS; Start-VMS }
}
