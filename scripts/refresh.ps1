# Macro Dashboard — scheduled refresh (Tue/Fri 7:00 AM).
# Run from Task Scheduler or manually. Uses project root so refresh.py finds config and modules.
$ErrorActionPreference = "Stop"
# Project root = parent of the folder containing this script (scripts/)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ProjectRoot) { $ProjectRoot = (Get-Location).Path }
Set-Location $ProjectRoot

# Optional: load .env into process (refresh.py also loads via python-dotenv)
if (Test-Path (Join-Path $ProjectRoot ".env")) {
    Get-Content (Join-Path $ProjectRoot ".env") | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) {
    Write-Error "python or py not found. Install Python and ensure it is on PATH."
    exit 1
}

& $python.Source refresh.py @args
exit $LASTEXITCODE
