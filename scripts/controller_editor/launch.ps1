# One-shot launcher for the controller web editor.
#
# What it does, in order:
#   1. Find or create venv\ at the repo root (uses `python` on PATH).
#   2. Install requirements.txt + host\requirements.txt if anything is missing.
#   3. Launch `python -m host.controller_web_editor` and open a browser.
#
# Idempotent: re-running just re-launches the server.  Skips pip when
# the install stamp matches.

$ErrorActionPreference = 'Stop'

# Repo root = parent of scripts\controller_editor
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $RepoRoot

$Venv = Join-Path $RepoRoot 'venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$Stamp = Join-Path $Venv '.controller_editor_install.stamp'

function Find-SystemPython {
    foreach ($name in @('py', 'python', 'python3')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            # `py` is the Windows launcher; pin to a 3.x interpreter.
            if ($name -eq 'py') { return @($cmd.Source, '-3') }
            return @($cmd.Source)
        }
    }
    throw "No Python interpreter found on PATH.  Install Python 3.10+ from https://python.org and retry."
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating venv at $Venv ..." -ForegroundColor Cyan
    $sysPy = Find-SystemPython
    & $sysPy[0] $sysPy[1..($sysPy.Length - 1)] -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed" }
    Remove-Item $Stamp -ErrorAction SilentlyContinue
}

# Hash of the requirements files; install only when it changes.
$reqFiles = @(
    Join-Path $RepoRoot 'requirements.txt'
    Join-Path $RepoRoot 'host\requirements.txt'
)
$reqHash = (Get-FileHash -Algorithm SHA1 $reqFiles | ForEach-Object Hash) -join ','

$needInstall = $true
if (Test-Path $Stamp) {
    if ((Get-Content $Stamp -Raw).Trim() -eq $reqHash) { $needInstall = $false }
}

if ($needInstall) {
    Write-Host "Installing Python deps (this only re-runs when requirements change) ..." -ForegroundColor Cyan
    & $VenvPython -m pip install --upgrade pip --quiet
    foreach ($req in $reqFiles) {
        & $VenvPython -m pip install -r $req --quiet
        if ($LASTEXITCODE -ne 0) { throw "pip install failed for $req" }
    }
    Set-Content -Path $Stamp -Value $reqHash -Encoding ascii
}

# Open the browser shortly after the server starts listening.  Background
# job so the main shell stays attached to the server's stdout.
$port = 8071
Start-Job -ScriptBlock {
    param($p)
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 250
        if (Test-NetConnection -ComputerName 127.0.0.1 -Port $p -InformationLevel Quiet -WarningAction SilentlyContinue) {
            Start-Process "http://127.0.0.1:$p"
            return
        }
    }
} -ArgumentList $port | Out-Null

Write-Host "Starting server on http://127.0.0.1:$port (Ctrl+C to stop)" -ForegroundColor Green
& $VenvPython -m host.controller_web_editor --port $port
