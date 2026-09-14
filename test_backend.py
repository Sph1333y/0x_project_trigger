"""
test_backend.py
===============
Unit and integration tests for the FastAPI Attendance backend with strict security,
Header-only API Key validation, Literal[0, 1] flag validation, read-only GET /flag,
and concurrency guarding.
"""

import os
import json
from unittest.mock import patch
from fastapi.testclient import TestClient

# Ensure test environment has ATTENDANCE_API_KEY set before importing app
os.environ["ATTENDANCE_API_KEY"] = "test_secret_key_12345"

from main import app, _submission_lock
from flag_manager import get_flag, set_flag, FLAG_FILE_PATH
import submit_attendance

client = TestClient(app)
VALID_API_KEY = "test_secret_key_12345"
AUTH_HEADERS = {"X-API-Key": VALID_API_KEY}


def test_public_health_and_root():
    # 1. Public health check
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    # 2. Public root endpoint (does not leak internal flag or secrets)
    res = client.get("/")
    assert res.status_code == 200
    assert res.json() == {
        "service": "Attendance Automation Backend",
        "status": "online"
    }


def test_authentication_enforcement():
    # 3. /status without API key returns 401
    res = client.get("/status")
    assert res.status_code == 401

    # 4. /status with wrong API key returns 401
    res = client.get("/status", headers={"X-API-Key": "wrong_key_xyz"})
    assert res.status_code == 401

    # Query param ?api_key= must NOT work (Header-only authentication)
    res = client.get(f"/status?api_key={VALID_API_KEY}")
    assert res.status_code == 401

    # 5. /status with correct X-API-Key returns 200
    set_flag(0)
    res = client.get("/status", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == {"flag": 0, "status": "ok"}


def test_flag_mutation_and_validation():
    # 6. POST /flag with {"flag": 1} works
    res = client.post("/flag", json={"flag": 1}, headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == {"flag": 1, "status": "ok"}
    assert get_flag() == 1

    # 7. POST /flag with {"flag": 0} works
    res = client.post("/flag", json={"flag": 0}, headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == {"flag": 0, "status": "ok"}
    assert get_flag() == 0

    # 8. Invalid flag values are strictly rejected (422 Unprocessable Entity)
    for invalid_val in [2, 5, -1, 999, "abc"]:
        res = client.post("/flag", json={"flag": invalid_val}, headers=AUTH_HEADERS)
        assert res.status_code == 422, f"Expected 422 for invalid flag value: {invalid_val}"

    # Flag remains unchanged (0)
    assert get_flag() == 0


def test_get_flag_is_readonly():
    set_flag(0)
    # 9. GET /flag returns current flag
    res = client.get("/flag", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == {"flag": 0, "status": "ok"}

    # 10. GET /flag?flag=1 must NOT change the flag
    res = client.get("/flag?flag=1", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == {"flag": 0, "status": "ok"}
    assert get_flag() == 0, "GET request must be strictly read-only!"


def test_shortcut_endpoints():
    # 11. POST /on sets flag to 1
    res = client.post("/on", json={}, headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == {"flag": 1, "status": "ok"}
    assert get_flag() == 1

    # 12. POST /off sets flag to 0
    res = client.post("/off", json={}, headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == {"flag": 0, "status": "ok"}
    assert get_flag() == 0


def test_submit_endpoint_and_guards():
    # 13. POST /submit is protected
    res = client.post("/submit", json={})
    assert res.status_code == 401

    # 14. Flag guard prevents submission when flag == 0
    set_flag(0)
    res = client.post("/submit", json={"student_id": "test123"}, headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json()["status"] == "error"
    assert "Flag is 0 (OFF)" in res.json()["message"]

    # Direct function flag guard test
    success, status_code, data = submit_attendance.run_pipeline(student_id="test123")
    assert success is False
    assert status_code == "FLAG_DISABLED"

    # 15. Concurrency guard prevents duplicate simultaneous submissions
    set_flag(1)
    acquired = _submission_lock.acquire(blocking=False)
    assert acquired is True
    try:
        res = client.post("/submit", json={"student_id": "test123"}, headers=AUTH_HEADERS)
        assert res.status_code == 200
        assert res.json()["status"] == "busy"
        assert "submission process is currently in progress" in res.json()["message"]
    finally:
        _submission_lock.release()
        set_flag(0)


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING BACKEND UNIT & INTEGRATION TESTS")
    print("=" * 60)
    test_public_health_and_root()
    print("[PASS] Public Health & Root endpoints verified.")
    test_authentication_enforcement()
    print("[PASS] Header-only Authentication verified.")
    test_flag_mutation_and_validation()
    print("[PASS] Flag Mutation & Strict Literal[0, 1] Validation verified.")
    test_get_flag_is_readonly()
    print("[PASS] Read-only GET /flag verified.")
    test_shortcut_endpoints()
    print("[PASS] Shortcut endpoints /on and /off verified.")
    test_submit_endpoint_and_guards()
    print("[PASS] Flag Guard and Submission Concurrency Guard verified.")
    print("=" * 60)
    print("ALL TESTS COMPLETED SUCCESSFULLY (100% PASS)!")
    print("=" * 60)
