"""
main.py — FastAPI Backend for Attendance System with API Key Security
======================================================================
Hosted on AWS EC2 to interface with the Flutter mobile application.

Features:
  - Header & Query API Key authentication (`X-API-Key` or `?api_key=...`).
  - Receives toggle commands from Flutter (flag=1 for ON, flag=0 for OFF).
  - Updates and reads flag_data.json safely via flag_manager.
  - Returns exact JSON response: {"flag": 1, "status": "ok"} or {"flag": 0, "status": "ok"}
  - Fully CORS-enabled for Flutter mobile & web clients.
  - Option to trigger attendance submission in the background when flag is turned ON.

Endpoints:
  POST /flag          -> Set flag via JSON body {"flag": 1} or query param ?flag=1
  GET  /flag          -> Read current flag or set via ?flag=1
  POST /on            -> Shortcut to turn flag ON (flag=1)
  POST /off           -> Shortcut to turn flag OFF (flag=0)
  GET  /status        -> Health check & current status
  POST /submit        -> Manually trigger attendance pipeline in background
"""

import os
import logging
from typing import Optional
from fastapi import FastAPI, BackgroundTasks, Query, Body, HTTPException, Security, Depends, status
from fastapi.security import APIKeyHeader, APIKeyQuery
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from flag_manager import get_flag, set_flag
import submit_attendance

# ─── Load .env file automatically if present ─────────────────────────────────
def _load_env_file():
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass

_load_env_file()

# ─── API Key Configuration ───────────────────────────────────────────────────
# Reads API key from environment variable (or .env). 
# Fallback is only for local development if not set.
API_KEY_ENV = os.getenv("ATTENDANCE_API_KEY", "change_this_secret_key_in_production")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)


def verify_api_key(
    header_key: Optional[str] = Security(api_key_header),
    query_key: Optional[str] = Security(api_key_query)
):
    """
    Validates API key provided in either:
      1. HTTP Header: 'X-API-Key: <your_key>'
      2. URL Query Param: '?api_key=<your_key>'
    """
    key = header_key or query_key
    if not key or key != API_KEY_ENV:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key. Provide 'X-API-Key' header or '?api_key=' parameter."
        )
    return key


# ─── Logging Setup ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("attendance_backend")

# ─── FastAPI App Initialization ──────────────────────────────────────────────
app = FastAPI(
    title="Attendance System Backend",
    description="Backend service running on AWS EC2 connecting Flutter to attendance automation.",
    version="1.0.0"
)

# Enable CORS for Flutter mobile/web connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request & Response Models ───────────────────────────────────────────────
class FlagRequest(BaseModel):
    flag: int = Field(..., description="1 for ON, 0 for OFF")
    student_id: Optional[str] = Field("test123", description="Student ID to submit if triggering attendance")
    auto_trigger: Optional[bool] = Field(False, description="Automatically trigger attendance in background if flag=1")

    class Config:
        json_schema_extra = {
            "example": {
                "flag": 1,
                "student_id": "test123",
                "auto_trigger": False
            }
        }


class FlagResponse(BaseModel):
    flag: int
    status: str


# ─── Background Worker ───────────────────────────────────────────────────────
def background_submit_task(student_id: str):
    """Executes the attendance pipeline in the background."""
    logger.info(f"[Background Task] Triggering attendance submission for student: {student_id}")
    try:
        success, status_code, data = submit_attendance.run_pipeline(student_id=student_id)
        logger.info(f"[Background Task] Completed with status: {status_code}, success: {success}")
    except Exception as e:
        logger.error(f"[Background Task] Error during execution: {e}")


# ─── API Endpoints ───────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    """Public root endpoint (health check)."""
    current_flag = get_flag()
    return {
        "service": "Attendance Automation Backend",
        "status": "online",
        "flag": current_flag,
        "auth": "API Key required for protected endpoints (/status, /flag, /on, /off, /submit)"
    }


@app.get("/status", response_model=FlagResponse, tags=["Flag Management"], dependencies=[Depends(verify_api_key)])
def get_status():
    """Returns the current flag status."""
    current_flag = get_flag()
    return FlagResponse(flag=current_flag, status="ok")


@app.post("/flag", response_model=FlagResponse, tags=["Flag Management"], dependencies=[Depends(verify_api_key)])
def set_flag_post(
    request: Optional[FlagRequest] = Body(None),
    flag: Optional[int] = Query(None, description="Flag: 1 for ON, 0 for OFF"),
    student_id: Optional[str] = Query("test123", description="Student ID"),
    auto_trigger: Optional[bool] = Query(False, description="Trigger attendance if flag=1"),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Sets the flag to 1 (ON) or 0 (OFF).
    Accepts JSON body `{"flag": 1}` or query parameter `?flag=1`.
    Returns: `{"flag": 1, "status": "ok"}`
    """
    target_flag = None
    target_student = student_id
    trigger = auto_trigger

    if request is not None:
        target_flag = request.flag
        if request.student_id:
            target_student = request.student_id
        if request.auto_trigger is not None:
            trigger = request.auto_trigger
    elif flag is not None:
        target_flag = flag

    if target_flag is None:
        raise HTTPException(status_code=400, detail="Missing 'flag' parameter (must be 1 or 0)")

    clean_val = 1 if int(target_flag) == 1 else 0
    saved_val = set_flag(clean_val)
    logger.info(f"[API] Set flag -> {saved_val}")

    if saved_val == 1 and trigger:
        background_tasks.add_task(background_submit_task, target_student)

    return FlagResponse(flag=saved_val, status="ok")


@app.get("/flag", response_model=FlagResponse, tags=["Flag Management"], dependencies=[Depends(verify_api_key)])
def get_or_set_flag_get(
    flag: Optional[int] = Query(None, description="Optional: 1 for ON, 0 for OFF"),
    student_id: Optional[str] = Query("test123"),
    auto_trigger: Optional[bool] = Query(False),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    GET endpoint for Flutter compatibility:
      - Calling `/flag` returns current flag: `{"flag": 0, "status": "ok"}`
      - Calling `/flag?flag=1` sets flag to 1 and returns: `{"flag": 1, "status": "ok"}`
    """
    if flag is not None:
        clean_val = 1 if int(flag) == 1 else 0
        saved_val = set_flag(clean_val)
        logger.info(f"[API GET] Set flag -> {saved_val}")

        if saved_val == 1 and auto_trigger:
            background_tasks.add_task(background_submit_task, student_id)

        return FlagResponse(flag=saved_val, status="ok")

    current_flag = get_flag()
    return FlagResponse(flag=current_flag, status="ok")


@app.post("/on", response_model=FlagResponse, tags=["Convenience Shortcuts"], dependencies=[Depends(verify_api_key)])
def turn_on(
    student_id: Optional[str] = Query("test123"),
    auto_trigger: Optional[bool] = Query(False),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Shortcut endpoint to turn ON (flag=1)."""
    saved_val = set_flag(1)
    logger.info("[API] Turn ON (flag=1)")
    if auto_trigger:
        background_tasks.add_task(background_submit_task, student_id)
    return FlagResponse(flag=saved_val, status="ok")


@app.post("/off", response_model=FlagResponse, tags=["Convenience Shortcuts"], dependencies=[Depends(verify_api_key)])
def turn_off():
    """Shortcut endpoint to turn OFF (flag=0)."""
    saved_val = set_flag(0)
    logger.info("[API] Turn OFF (flag=0)")
    return FlagResponse(flag=saved_val, status="ok")


@app.post("/submit", tags=["Attendance Execution"], dependencies=[Depends(verify_api_key)])
def trigger_submission_now(
    student_id: str = Query("test123", description="Student ID to submit"),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Triggers the attendance submission pipeline.
    Note: The pipeline will immediately abort if flag == 0 in flag_data.json.
    """
    current_flag = get_flag()
    if current_flag != 1:
        return {
            "status": "error",
            "message": "Flag is 0 (OFF). Please turn flag ON before submitting.",
            "flag": current_flag
        }

    background_tasks.add_task(background_submit_task, student_id)
    return {
        "status": "ok",
        "message": f"Attendance submission initiated in background for {student_id}",
        "flag": current_flag
    }


if __name__ == "__main__":
    import uvicorn
    # Bind to 0.0.0.0 so local network, EC2, and Flutter clients can connect
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
