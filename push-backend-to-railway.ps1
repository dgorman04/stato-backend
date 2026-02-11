# Sync backend to stato-backend-deploy and push to Railway's repo (stato-backend).
# Run from: "Project Learning" or "Project Learning/backend".
# Usage: .\push-backend-to-railway.ps1
#        .\push-backend-to-railway.ps1 "Your commit message"

$ErrorActionPreference = "Stop"
$projectRoot = if (Test-Path (Join-Path $PSScriptRoot "..\stato-backend-deploy")) { $PSScriptRoot | Split-Path -Parent } else { $PSScriptRoot }
$backendSrc = Join-Path $projectRoot "backend"
$deployDir = Join-Path $projectRoot "stato-backend-deploy"

if (-not (Test-Path $backendSrc)) { Write-Error "Backend folder not found: $backendSrc" }
if (-not (Test-Path $deployDir)) { Write-Error "stato-backend-deploy not found: $deployDir" }

# Copy only what deploy needs (avoid overwriting .env / db.sqlite3 in deploy)
$rootFiles = @("manage.py", "requirements.txt", "Procfile", "railway.json", ".env.example", "package-lock.json")
foreach ($f in $rootFiles) {
    $src = Join-Path $backendSrc $f
    if (Test-Path $src) { Copy-Item $src (Join-Path $deployDir $f) -Force }
}
Copy-Item (Join-Path $backendSrc "backend") (Join-Path $deployDir "backend") -Recurse -Force
Copy-Item (Join-Path $backendSrc "stato") (Join-Path $deployDir "stato") -Recurse -Force

$msg = if ($args[0]) { $args[0] } else { "Sync backend from Project Learning" }
Push-Location $deployDir
try {
    git add -A
    $status = git status --short
    if (-not $status) { Write-Host "No changes to push."; exit 0 }
    git commit -m $msg
    git push origin main
    Write-Host "Pushed to stato-backend (Railway)."
} finally {
    Pop-Location
}
