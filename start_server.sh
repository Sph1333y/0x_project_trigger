#!/bin/bash
# ==============================================================================
# start_server.sh — Startup script for AWS EC2 Linux instance
# ==============================================================================

# Exit on error
set -e

# Change to the directory of this script
cd "$(dirname "$0")"

# Activate virtualenv if available
if [ -d "venv" ]; then
    echo "Activating virtualenv..."
    source venv/bin/activate
fi

echo "Starting FastAPI Attendance Server on 0.0.0.0:8000..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
