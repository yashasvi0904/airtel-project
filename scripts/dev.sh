#!/usr/bin/env bash
# Start backend (:8000) and frontend (:3000) for local development on macOS/Linux/Git-Bash.
root="$(cd "$(dirname "$0")/.." && pwd)"
py="$root/backend/.venv/bin/python"; [ -x "$py" ] || py="$root/backend/.venv/Scripts/python"
(cd "$root/backend" && "$py" -m uvicorn app.main:app --port 8000 --reload) &
(cd "$root/frontend" && npm run dev -- -p 3000) &
wait
