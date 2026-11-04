# Start backend (:8000) and frontend (:3000) for local development on Windows.
$root = Split-Path -Parent $PSScriptRoot
Start-Process -WorkingDirectory "$root\backend" -FilePath "$root\backend\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","app.main:app","--port","8000","--reload"
Start-Process -WorkingDirectory "$root\frontend" -FilePath "npm.cmd" -ArgumentList "run","dev","--","-p","3000"
Write-Host "Backend http://localhost:8000/docs  |  Frontend http://localhost:3000"
