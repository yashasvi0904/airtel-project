# Share the prototype through a public HTTPS link (Cloudflare quick tunnel; no account needed).
#   powershell -ExecutionPolicy Bypass -File scripts\share_demo.ps1
# The link works only while this PC is on and this script's processes are running.
#
# Safety for a public link: a FRESH demo database + upload folder (storage\demo, wiped on every run),
# random JWT / encryption / admin secrets for this run only (the repo's dev defaults are public),
# backend bound to 127.0.0.1 (only the Next.js proxy is exposed), payments stay on the sandbox gateway.
# Sample orders are seeded by scripts\seed_demo.py. The server-side Gemini key from .env is still used for the advisor (visitors spend its free quota).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$demo = "$root\storage\demo"
$py = "$root\backend\.venv\Scripts\python.exe"

Get-NetTCPConnection -LocalPort 8000, 3000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
if (Test-Path $demo) { Remove-Item -Recurse -Force $demo }
New-Item -ItemType Directory -Force "$demo\uploads" | Out-Null

function New-Secret([int]$n) { -join ((48..57) + (65..90) + (97..122) | Get-Random -Count $n | ForEach-Object { [char]$_ }) }
$adminPw = New-Secret 14
$env:DATABASE_URL = "sqlite:///$(($demo -replace '\\','/'))/udyam.db"
$env:UPLOAD_DIR = "$demo\uploads"
$env:JWT_SECRET = New-Secret 48
$env:ENCRYPTION_KEY = (& $py -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())").Trim()
$env:ADMIN_PASSWORD = $adminPw
$env:PAYMENT_WEBHOOK_SECRET = New-Secret 32
$env:ENVIRONMENT = "development"   # sandbox payments refuse "production"
"admin@accel.example / $adminPw" | Set-Content "$demo\admin-login.txt"

Write-Host "Building frontend (production)..."
Push-Location "$root\frontend"; npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }; Pop-Location

Start-Process -WorkingDirectory "$root\backend" -FilePath $py -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -RedirectStandardOutput "$demo\backend.log" -RedirectStandardError "$demo\backend.err.log" -WindowStyle Hidden
Start-Process -WorkingDirectory "$root\frontend" -FilePath "npm.cmd" -ArgumentList "run", "start", "--", "-p", "3000" -RedirectStandardOutput "$demo\frontend.log" -RedirectStandardError "$demo\frontend.err.log" -WindowStyle Hidden
for ($i = 0; $i -lt 60; $i++) {
    try { if ((Invoke-WebRequest -UseBasicParsing http://localhost:3000/api/health -TimeoutSec 3).StatusCode -eq 200) { break } } catch {}
    Start-Sleep -Seconds 2
}

# Sample customers/orders/KYC cases so the admin dashboard has a real workflow to show (all synthetic, created through the API).
& $py "$root\scripts\seed_demo.py" --api http://127.0.0.1:8000/api --admin-password $adminPw
if ($LASTEXITCODE -ne 0) { Write-Warning "demo data was not created (see message above); the app still works, the admin lists will just be empty" }

$cf = "$env:LOCALAPPDATA\cloudflared\cloudflared.exe"
if (-not (Test-Path $cf)) {
    New-Item -ItemType Directory -Force (Split-Path $cf) | Out-Null
    Invoke-WebRequest -UseBasicParsing "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $cf
}
Start-Process -FilePath $cf -ArgumentList "tunnel", "--url", "http://localhost:3000", "--no-autoupdate" -RedirectStandardError "$demo\tunnel.log" -RedirectStandardOutput "$demo\tunnel.out.log" -WindowStyle Hidden
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    $m = Select-String -Path "$demo\tunnel.log" -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($m) { $url = $m.Matches[0].Value; break }
}
if (-not $url) { throw "tunnel did not report a URL, see $demo\tunnel.log" }
$url | Set-Content "$demo\public-url.txt"
Write-Host "`nPublic demo link: $url`nAdmin login: $demo\admin-login.txt`nStop: close the cloudflared/uvicorn/node processes (or re-run this script)."
