@echo off
REM ==============================================================================
REM start_server.bat — Windows Local Testing Script
REM ==============================================================================

cd /d "%~dp0"
echo Starting FastAPI Attendance Server on http://127.0.0.1:8000 ...
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
