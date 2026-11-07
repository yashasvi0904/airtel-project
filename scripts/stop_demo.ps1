# Stop everything started by share_demo.ps1 (and dev.ps1): backend :8000, frontend :3000 and the public tunnel.
#   powershell -ExecutionPolicy Bypass -File scripts\stop_demo.ps1
Get-NetTCPConnection -LocalPort 8000, 3000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Get-Process -Name cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1
$left = Get-NetTCPConnection -LocalPort 8000, 3000 -State Listen -ErrorAction SilentlyContinue
if ($left -or (Get-Process -Name cloudflared -ErrorAction SilentlyContinue)) { Write-Host "Something is still running - run this again." } else { Write-Host "Stopped: backend, frontend and the public link are off." }
