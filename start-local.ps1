<#
One-command local dev launcher: starts the backend, the frontend, and
LeafSense (the separate vision service the Diagnose page depends on) —
each in its own visible console window, so their logs stay readable
instead of interleaved in one stream.

Why this exists: the recurring failure mode was "Diagnose says the plant
service isn't running" because LeafSense is a separate sibling repo/process
that's easy to forget to start on its own (see
app/services/vision_client.py's docstring for why it's kept separate:
InsightAI never imports TensorFlow or any LeafSense code). This script
makes "start everything for local dev" one command instead of three.

LeafSense is optional: if the sibling ../LeafSense checkout isn't present
(e.g. a portfolio visitor who only cloned InsightAI-RAG), this script
starts backend + frontend anyway and just skips it with a note — Diagnose
will show its existing friendly "service isn't running" message, same as
today, nothing new breaks.

Usage (from the InsightAI-RAG repo root):
    .\start-local.ps1

Each window is independent — closing/Ctrl+C one doesn't stop the others.
#>

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$leafSenseStart = Join-Path $repoRoot "..\LeafSense\backend\start.ps1"
$devRestart = Join-Path $backendDir "scripts\dev_restart.ps1"

Write-Host "[start-local] Launching backend (port 8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "& '$devRestart'"
)

Write-Host "[start-local] Launching frontend (Vite, port 5173 or next free)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$frontendDir'; npm run dev"
)

if (Test-Path $leafSenseStart) {
    Write-Host "[start-local] Launching LeafSense (port 8001)..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-Command",
        "& '$leafSenseStart'"
    )
} else {
    Write-Host "[start-local] Skipping LeafSense - no checkout found at $leafSenseStart" -ForegroundColor Yellow
    Write-Host "[start-local] The Diagnose page will show its normal 'service isn't running' message until LeafSense is cloned alongside this repo." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[start-local] All available services are starting in their own windows." -ForegroundColor Green
Write-Host "[start-local] Backend health:  http://localhost:8000/health"
Write-Host "[start-local] Frontend:        check the frontend window for its actual port (5173, or the next free one)"
Write-Host "[start-local] LeafSense:       http://localhost:8001/model-info"
