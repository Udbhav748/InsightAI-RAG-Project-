<#
.SYNOPSIS
One-command local dev launcher: starts the backend, frontend, and LeafSense vision service in parallel.

Services:
- Backend:          FastAPI on http://localhost:8000
- Frontend:         Vite React app on http://localhost:5173
- LeafSense Vision: FastAPI on http://localhost:8001 (plant leaf disease diagnosis)

Usage (from the InsightAI-RAG repo root):
    .\start-local.ps1
#>

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$leafSenseStart = Join-Path $repoRoot "..\LeafSense\backend\start.ps1"
$devRestart = Join-Path $backendDir "scripts\dev_restart.ps1"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  InsightAI-RAG & LeafSense Unified Local Launcher" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Launch Backend (FastAPI on http://localhost:8000)
Write-Host "[1/3] Launching Backend (FastAPI on http://localhost:8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "& '$devRestart'"
)

# 2. Launch Frontend (Vite on http://localhost:5173)
Write-Host "[2/3] Launching Frontend (Vite on http://localhost:5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$frontendDir'; npm run dev"
)

# 3. Launch LeafSense Vision Service (FastAPI on http://localhost:8001)
if (Test-Path $leafSenseStart) {
    Write-Host "[3/3] Launching LeafSense Vision Service (FastAPI on http://localhost:8001)..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "& '$leafSenseStart'"
    )
} else {
    Write-Host "[3/3] Skipping LeafSense - no checkout found at $leafSenseStart" -ForegroundColor Yellow
    Write-Host "      (Diagnose page will show fallback status until LeafSense is available)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "------------------------------------------------------------" -ForegroundColor Green
Write-Host "All services launched in parallel console windows!" -ForegroundColor Green
Write-Host "  • Backend API:        http://localhost:8000 (Health: http://localhost:8000/health, Docs: http://localhost:8000/docs)" -ForegroundColor White
Write-Host "  • Frontend UI:        http://localhost:5173" -ForegroundColor White
Write-Host "  • LeafSense Vision:   http://localhost:8001 (Model Info: http://localhost:8001/model-info)" -ForegroundColor White
Write-Host "------------------------------------------------------------" -ForegroundColor Green
