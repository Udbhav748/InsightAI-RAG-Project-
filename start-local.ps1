<#
.SYNOPSIS
One-command local dev launcher: starts the backend, frontend, and LeafSense vision service in parallel.

Services:
- Backend:          FastAPI on http://localhost:8000
- Frontend:         Vite React app on http://localhost:5173
- LeafSense Vision: FastAPI on http://localhost:8001 (plant leaf disease diagnosis)

Usage (from the InsightAI-RAG repo root):
    .\start-local.ps1
    or double-click start.bat
#>

$ErrorActionPreference = "Continue"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"

# Locate LeafSense directory
$leafSenseCandidates = @(
    (Join-Path (Split-Path -Parent $repoRoot) "LeafSense\backend\start.ps1"),
    (Join-Path $repoRoot "LeafSense\backend\start.ps1"),
    (Join-Path $repoRoot "..\LeafSense\backend\start.ps1")
)

$leafSenseStart = $null
foreach ($cand in $leafSenseCandidates) {
    if (Test-Path $cand) {
        $leafSenseStart = (Resolve-Path $cand).Path
        break
    }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  InsightAI-RAG & LeafSense Unified Local Launcher" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Launch LeafSense Vision Service (FastAPI on http://localhost:8001)
if ($leafSenseStart) {
    Write-Host "[1/3] Launching LeafSense Vision Service (Port 8001)..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-Command",
        "& '$leafSenseStart'"
    )
} else {
    Write-Host "[1/3] LeafSense repo not found in adjacent folder (Backend will use auto-recovery / cloud fallback)." -ForegroundColor Yellow
}

# 2. Launch Backend (FastAPI on http://localhost:8000)
Write-Host "[2/3] Launching Backend (FastAPI on http://localhost:8000)..." -ForegroundColor Cyan
$devRestart = Join-Path $backendDir "scripts\dev_restart.ps1"
if (Test-Path $devRestart) {
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-Command",
        "& '$devRestart'"
    )
} else {
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-ExecutionPolicy", "Bypass", "-Command",
        "Set-Location '$backendDir'; python -m uvicorn app.main:app --host localhost --port 8000 --reload"
    )
}

# 3. Launch Frontend (Vite on http://localhost:5173)
Write-Host "[3/3] Launching Frontend (Vite on http://localhost:5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass", "-Command",
    "Set-Location '$frontendDir'; npm run dev"
)

Write-Host ""
Write-Host "------------------------------------------------------------" -ForegroundColor Green
Write-Host "All services launched in parallel console windows!" -ForegroundColor Green
Write-Host "  • Backend API:        http://localhost:8000 (Health: http://localhost:8000/health)" -ForegroundColor White
Write-Host "  • Frontend UI:        http://localhost:5173" -ForegroundColor White
Write-Host "  • LeafSense Vision:   http://localhost:8001 (Health: http://localhost:8001/model-info)" -ForegroundColor White
Write-Host "------------------------------------------------------------" -ForegroundColor Green
