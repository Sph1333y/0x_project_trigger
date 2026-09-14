"""
main.py — FastAPI Backend for Attendance System (ARM64 / IPv6 / EC2)
====================================================================
Hosted on AWS EC2 (t4g.small ARM64, Ubuntu Server) to interface with the
Flutter mobile application.

Key Architectural Guarantees:
  - Header-only API key authentication (`X-API-Key`) with constant-time comparison.
  - Fail-fast at startup if ATTENDANCE_API_KEY environment variable is missing.
  - Strict validation on flag values: ONLY Literal[0, 1] accepted.
  - Read-only GET /flag and state-mutating POST /flag.
  - Public health check at GET /health (returns {"status": "ok"}).
  - Safe root endpoint GET / returning service info without leaking state.
  - Application-level concurrency guard preventing duplicate Chromium processes.
  - Conservative CORS policy: allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-API-Key"].
"""

import os
import sys
import secrets
import logging
import threading
from typing import Optional, Literal
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, Body, HTTPException, Security, Depends, status
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from flag_manager import get_flag, set_flag
import submit_attendance

# ─── Logging Setup ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("attendance_backend")


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


# ─── API Key Configuration (Fail-Fast) ───────────────────────────────────────
API_KEY_ENV = os.getenv("ATTENDANCE_API_KEY")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(
    header_key: Optional[str] = Security(api_key_header),
) -> str:
    """
    Validates API key strictly from the 'X-API-Key' HTTP Header using
    constant-time string comparison (secrets.compare_digest).
    Query-parameter authentication is intentionally NOT supported.
    """
    if not API_KEY_ENV:
        logger.critical("ATTENDANCE_API_KEY environment variable is not configured on the server.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server authentication configuration error."
        )

    if not header_key or not secrets.compare_digest(header_key, API_KEY_ENV):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key. Provide 'X-API-Key' header."
        )
    return header_key


# ─── Application Concurrency Guard ───────────────────────────────────────────
# Prevents simultaneous browser launches to protect 2 GiB RAM on t4g.small EC2.
_submission_lock = threading.Lock()


# ─── Request & Response Models ───────────────────────────────────────────────
class FlagRequest(BaseModel):
    flag: Literal[0, 1] = Field(..., description="Flag value must strictly be 0 (OFF) or 1 (ON)")
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
    flag: Literal[0, 1]
    status: str


class HealthResponse(BaseModel):
    status: str


class RootResponse(BaseModel):
    service: str
    status: str


# ─── Background Worker ───────────────────────────────────────────────────────
def background_submit_task(student_id: str):
    """Executes the attendance pipeline in the background with concurrency protection."""
    acquired = _submission_lock.acquire(blocking=False)
    if not acquired:
        logger.warning(f"[Background Task] Another attendance submission is already running. Skipping duplicate task for student: {student_id}")
        return

    try:
        logger.info(f"[Background Task] Starting attendance submission for student: {student_id}")
        success, status_code, data = submit_attendance.run_pipeline(student_id=student_id)
        logger.info(f"[Background Task] Finished with status: {status_code}, success: {success}")
    except Exception as e:
        logger.error(f"[Background Task] Unexpected error during execution: {e}")
    finally:
        _submission_lock.release()


# ─── FastAPI Lifespan (Startup Validation) ───────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate critical environment at startup
    if not API_KEY_ENV or not API_KEY_ENV.strip():
        logger.critical("FATAL: ATTENDANCE_API_KEY environment variable is missing or empty! Server cannot start securely.")
        raise RuntimeError("ATTENDANCE_API_KEY environment variable must be set.")
    logger.info("ATTENDANCE_API_KEY is verified and loaded successfully.")
    yield


# ─── FastAPI App Initialization ──────────────────────────────────────────────
app = FastAPI(
    title="Attendance System Backend",
    description="Backend service running on AWS EC2 ARM64 connecting Flutter to attendance automation.",
    version="1.0.0",
    lifespan=lifespan
)

# Conservative CORS policy for native mobile clients & protected environments
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


# ─── API Endpoints ───────────────────────────────────────────────────────────

@app.get("/", response_model=RootResponse, tags=["Health"])
def root():
    """Public root endpoint. Returns service identification without exposing internal state."""
    return RootResponse(
        service="Attendance Automation Backend",
        status="online"
    )


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health():
    """Simple public health check endpoint."""
    return HealthResponse(status="ok")


@app.get("/status", response_model=FlagResponse, tags=["Flag Management"], dependencies=[Depends(verify_api_key)])
def get_status():
    """Returns the current flag status (Protected by X-API-Key)."""
    current_flag = get_flag()
    return FlagResponse(flag=current_flag, status="ok")


@app.get("/flag", response_model=FlagResponse, tags=["Flag Management"], dependencies=[Depends(verify_api_key)])
def get_flag_endpoint():
    """
    Read-only endpoint to get current flag state.
    State mutation is strictly reserved for POST /flag.
    """
    current_flag = get_flag()
    return FlagResponse(flag=current_flag, status="ok")


@app.post("/flag", response_model=FlagResponse, tags=["Flag Management"], dependencies=[Depends(verify_api_key)])
def set_flag_endpoint(
    request: FlagRequest = Body(...),
    background_tasks: BackgroundTasks = None
):
    """
    Sets the flag to 1 (ON) or 0 (OFF).
    Accepts JSON body: `{"flag": 1}` or `{"flag": 0}`.
    Returns: `{"flag": 1, "status": "ok"}`
    """
    saved_val = set_flag(request.flag)
    logger.info(f"[API] Set flag -> {saved_val}")

    if saved_val == 1 and request.auto_trigger and background_tasks is not None:
        background_tasks.add_task(background_submit_task, request.student_id or "test123")

    return FlagResponse(flag=saved_val, status="ok")


@app.post("/on", response_model=FlagResponse, tags=["Convenience Shortcuts"], dependencies=[Depends(verify_api_key)])
def turn_on(
    student_id: Optional[str] = Body(default="test123", embed=True),
    auto_trigger: Optional[bool] = Body(default=False, embed=True),
    background_tasks: BackgroundTasks = None
):
    """Shortcut endpoint to turn ON (flag=1)."""
    saved_val = set_flag(1)
    logger.info("[API] Turn ON (flag=1)")
    if auto_trigger and background_tasks is not None:
        background_tasks.add_task(background_submit_task, student_id or "test123")
    return FlagResponse(flag=saved_val, status="ok")


@app.post("/off", response_model=FlagResponse, tags=["Convenience Shortcuts"], dependencies=[Depends(verify_api_key)])
def turn_off():
    """Shortcut endpoint to turn OFF (flag=0)."""
    saved_val = set_flag(0)
    logger.info("[API] Turn OFF (flag=0)")
    return FlagResponse(flag=saved_val, status="ok")


@app.post("/submit", tags=["Attendance Execution"], dependencies=[Depends(verify_api_key)])
def trigger_submission_now(
    student_id: Optional[str] = Body(default="test123", embed=True),
    background_tasks: BackgroundTasks = None
):
    """
    Manually triggers the attendance submission pipeline in background.
    Protected by concurrency guard and flag guard (aborts if flag == 0).
    """
    current_flag = get_flag()
    if current_flag != 1:
        return {
            "status": "error",
            "message": "Flag is 0 (OFF). Please turn flag ON before submitting.",
            "flag": current_flag
        }

    if _submission_lock.locked():
        return {
            "status": "busy",
            "message": "An attendance submission process is currently in progress. Please wait.",
            "flag": current_flag
        }

    if background_tasks is not None:
        background_tasks.add_task(background_submit_task, student_id or "test123")

    return {
        "status": "ok",
        "message": f"Attendance submission initiated in background for {student_id or 'test123'}",
        "flag": current_flag
    }


if __name__ == "__main__":
    import uvicorn
    # In local testing, bind to :: or 0.0.0.0 port 8000
    uvicorn.run("main:app", host="::", port=8000, reload=True, workers=1)
