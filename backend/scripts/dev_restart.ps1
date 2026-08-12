<#
Dev restart helper for the InsightAI-RAG backend (PowerShell / WSL users).

Fixes the two "restart" failure modes hit repeatedly in dev:

1. A previously-started uvicorn is still listening on port 8000, so the new
   one dies with "address already in use" (or, worse, binds somewhere unknown
   and silently races the old instance). This script finds and stops the
   existing listener before starting a fresh server.

2. Postgres is down (Docker Desktop not running, insightai-postgres container
   stopped), which makes the backend hang ~5s+ on its bounded connect then
   fail with a bare traceback. This scripts probes Postgres first and, if it
   is unreachable, prints the one actionable fix instead of starting uvicorn
   into an inevitable failure.

Replaces the manual `uvicorn app.main:app --reload` (the usual dev loop) —
run this from anywhere; it cd's to backend/ itself.

Usage:
    pwsh backend/scripts/dev_restart.ps1
#>

$ErrorActionPreference = "Stop"

$PORT = 8000
$TIMEOUT_MS = 3000
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir

# ---- 1. Free port 8000 if a previous instance is still listening ----------
$existing = Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $ownerId = $existing | Select-Object -First 1 -ExpandProperty OwningProcess
    $owner = Get-Process -Id $ownerId -ErrorAction SilentlyContinue
    if ($owner) {
        Write-Host "[dev_restart] Stopping previous listener on port $PORT (PID $ownerId, $($owner.ProcessName))..." -ForegroundColor Yellow
        Stop-Process -Id $ownerId -Force
        Start-Sleep -Seconds 1
    }
} else {
    Write-Host "[dev_restart] Port $PORT is free." -ForegroundColor Green
}

# ---- 2. Quick Postgres reachability probe --------------------------------
# Parse host/port out of backend/.env's DATABASE_URL so we check the real
# target, matching database_connect_timeout_seconds' fail-fast intent.
$dbHost = "localhost"
$dbPort = 5432
$envPath = Join-Path $backendDir ".env"
$dbUrlLine = Select-String -Path $envPath -Pattern '^\s*DATABASE_URL=' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($dbUrlLine) {
    $dbUrl = ($dbUrlLine.Line -split '=', 2)[1].Trim().Trim('"').Trim("'")
    if ($dbUrl -match '@([^:/]+):(\d+)') {
        $dbHost = $Matches[1]
        $dbPort = [int]$Matches[2]
    }
}

$tcp = New-Object System.Net.Sockets.TcpClient
try {
    $connectTask = $tcp.ConnectAsync($dbHost, $dbPort)
    $ok = $connectTask.Wait($TIMEOUT_MS)
    if (-not $ok -or -not $tcp.Connected) {
        Write-Error "Postgres unreachable at ${dbHost}:${dbPort} - is Docker Desktop / the insightai-postgres container running? Start Docker Desktop, then: docker start insightai-postgres"
        exit 1
    }
    Write-Host "[dev_restart] Postgres reachable at ${dbHost}:${dbPort}." -ForegroundColor Green
} finally {
    $tcp.Dispose()
}

# ---- 3. Start the dev server (the documented "usual dev loop") ------------
Push-Location $backendDir
try {
    Write-Host "[dev_restart] Starting backend: uvicorn app.main:app --reload" -ForegroundColor Cyan
    uvicorn app.main:app --reload
} finally {
    Pop-Location
}