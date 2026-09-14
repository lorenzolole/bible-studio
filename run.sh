#!/bin/bash
# TikTok Bible Studio Launcher
cd "$(dirname "$0")"

echo "=========================================="
echo "✝ TikTok Bible Studio — David Suchet Audio"
echo "=========================================="
echo "Iniciando servidor local en http://localhost:8000 ..."

# Open browser after 1.5 seconds in background
(sleep 1.5 && open "http://localhost:8000") &

# Start Uvicorn web server
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
