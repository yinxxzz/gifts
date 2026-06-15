#!/bin/bash
cd "$(dirname "$0")"
pkill -f "python3 server.py" 2>/dev/null || true
pkill -f "python3 -m http.server 8080" 2>/dev/null || true
nohup python3 server.py > server.log 2>&1 &
echo "Started server.py on :8080 (pid $!)"
