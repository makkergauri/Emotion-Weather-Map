# Starts the whole project with one command on Windows.
#
# Run it from the project root in PowerShell:
#     .\dev.ps1
#
# If Windows blocks it with an execution-policy error, this unblocks scripts for
# the current window only, which is the least invasive fix:
#     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#
# Everything here is idempotent — the venv, the pip install, the .env copy and
# the npm install are skipped if already done — so it's safe to run every time.

$ErrorActionPreference = "Stop"

$Root         = $PSScriptRoot
$BackendPort  = 8000
$FrontendPort = 5173

function Say  ($m) { Write-Host $m -ForegroundColor White }
function Note ($m) { Write-Host "   $m" -ForegroundColor DarkGray }
function Warn ($m) { Write-Host "   $m" -ForegroundColor Yellow }

# The backend runs as a background job. Without this cleanup it survives as an
# orphan holding port 8000, and the next run fails with "address already in use".
$BackendJob = $null
function Stop-Backend {
    if ($script:BackendJob) {
        Write-Host "`nStopping backend..." -ForegroundColor DarkGray
        Stop-Job   $script:BackendJob -ErrorAction SilentlyContinue
        Remove-Job $script:BackendJob -Force -ErrorAction SilentlyContinue
        $script:BackendJob = $null
    }
}

try {
    # --- prerequisites -------------------------------------------------------

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "python not found. Install Python 3.11+ from python.org and tick 'Add to PATH'."
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm not found. Install Node 18+ from nodejs.org."
    }

    # --- backend -------------------------------------------------------------

    Say "Backend"
    Set-Location "$Root\backend"

    if (-not (Test-Path ".venv")) {
        Note "creating virtual environment"
        python -m venv .venv
    }

    $Python = "$Root\backend\.venv\Scripts\python.exe"

    Note "checking Python packages"
    & $Python -m pip install -q -r requirements.txt

    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Warn "created backend\.env from the example"
        Warn "add your free NewsAPI key to it (https://newsapi.org/register),"
        Warn "or carry on without one — country pins will show as 'no data'."
    }

    if (Select-String -Path ".env" -Pattern "NEWS_API_KEY=your_key_here" -Quiet) {
        Warn "backend\.env still has the placeholder key, so countries will be grey."
        Warn "city drill-down works regardless — it needs no key."
    }

    Note "starting on http://127.0.0.1:$BackendPort"
    $BackendJob = Start-Job -ScriptBlock {
        param($py, $dir, $port)
        Set-Location $dir
        & $py -m uvicorn app.main:app --reload --port $port
    } -ArgumentList $Python, "$Root\backend", $BackendPort

    # Wait for it to answer before starting Vite, so the first page load doesn't
    # race the server and show a connection error.
    Write-Host "   waiting for the API" -NoNewline -ForegroundColor DarkGray
    $ready = $false
    foreach ($i in 1..40) {
        try {
            Invoke-WebRequest "http://127.0.0.1:$BackendPort/api/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
            $ready = $true
            break
        } catch {
            if ($BackendJob.State -eq "Failed") {
                Receive-Job $BackendJob
                throw "Backend exited during startup. See the error above."
            }
            Write-Host "." -NoNewline
            Start-Sleep -Milliseconds 500
        }
    }
    if ($ready) { Write-Host " ready" -ForegroundColor Green } else { Write-Host "" }

    # --- frontend ------------------------------------------------------------

    Write-Host ""
    Say "Frontend"
    Set-Location "$Root\frontend"

    if (-not (Test-Path "node_modules")) {
        Note "installing npm packages (first run only, takes a minute)"
        npm install --no-fund --no-audit
    }

    Write-Host ""
    Say "Open http://localhost:$FrontendPort"
    Note "pins fill in over ~30s on a cold cache — that's the warm-up, not a fault"
    Note "Ctrl+C stops both servers"
    Write-Host ""

    # Foreground, so Ctrl+C lands here and the finally block stops the backend.
    npm run dev -- --port $FrontendPort
}
finally {
    Stop-Backend
    Set-Location $Root
}
