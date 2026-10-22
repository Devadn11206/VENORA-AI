# ==============================================================================
# VENORA AI — Backend Development Server Launcher (Windows PowerShell)
# ==============================================================================
[CmdletBinding()]
param (
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload = $true
)

$ErrorActionPreference = "Stop"

# 1. Resolve repository root relative to this script's directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..")
$BackendDir = Join-Path $ProjectRoot "backend"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "                VENORA AI — Phase 1 Backend                 " -ForegroundColor Cyan
Write-Host "       Think. Execute. Evolve. | Local Development Server   " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "[INFO] Project root: $ProjectRoot"
Write-Host "[INFO] Backend dir:  $BackendDir"

# 2. Locate Python executable in .venv or system
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PythonExe = $null

if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
    Write-Host "[INFO] Using virtual environment Python: $VenvPython" -ForegroundColor Green
} else {
    $SystemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($SystemPython) {
        $PythonExe = "python"
        Write-Host "[WARNING] .venv not found. Using system Python." -ForegroundColor Yellow
    } else {
        Write-Host "[ERROR] Python was not found on your system or in .venv." -ForegroundColor Red
        Write-Host "[GUIDANCE] Please create a virtual environment first:"
        Write-Host "           python -m venv .venv"
        Write-Host "           .venv\Scripts\pip install -r backend\requirements.txt"
        exit 1
    }
}

# 3. Verify core dependencies are installed
Write-Host "[INFO] Verifying backend dependencies..."
$VerifyCommand = "$PythonExe -c ""import fastapi, uvicorn, sqlalchemy, pydantic, pydantic_settings; print('Dependencies OK')"""
try {
    $VerifyOutput = Invoke-Expression $VerifyCommand
    Write-Host "[INFO] $VerifyOutput" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Missing required dependencies!" -ForegroundColor Red
    Write-Host "[GUIDANCE] Install required packages with:"
    Write-Host "           $PythonExe -m pip install -r backend\requirements.txt"
    exit 1
}

# 4. Ensure data and logs directories exist
$DataDir = Join-Path $ProjectRoot "data"
$LogsDir = Join-Path $ProjectRoot "logs"

if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
}
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir -Force | Out-Null
}

# 5. Launch uvicorn from backend directory
Write-Host "[INFO] Starting server on http://$HostAddress:$Port (Reload: $Reload)..." -ForegroundColor Cyan
Write-Host "[INFO] OpenAPI documentation will be available at http://$HostAddress:$Port/docs"
Write-Host "[INFO] Press Ctrl+C to terminate."
Write-Host "------------------------------------------------------------"

Set-Location $BackendDir

$UvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $HostAddress, "--port", "$Port")
if ($Reload) {
    $UvicornArgs += "--reload"
}

& $PythonExe $UvicornArgs
