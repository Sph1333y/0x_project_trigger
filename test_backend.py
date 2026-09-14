"""
test_backend.py
===============
Unit and integration tests for the FastAPI Attendance backend with API Key security.
"""

import os
import json
from fastapi.testclient import TestClient
from main import app, API_KEY_ENV
from flag_manager import get_flag, set_flag, FLAG_FILE_PATH
import submit_attendance

client = TestClient(app)
AUTH_HEADERS = {"X-API-Key": API_KEY_ENV}


def test_flag_lifecycle():
    print("\n[Test 1] Testing Public Root endpoint...")
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "online"
    print("  -> Passed!")

    print("\n[Test 2] Testing Unauthorized Access (No API Key)...")
    res = client.get("/status")
    assert res.status_code == 401
    res = client.post("/flag", json={"flag": 1})
    assert res.status_code == 401
    print("  -> Passed! Unauthorized requests properly rejected with 401.")

    print("\n[Test 3] Testing Status with Header API Key...")
    set_flag(0)
    res = client.get("/status", headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == {"flag": 0, "status": "ok"}
    print("  -> Passed! Response: ", res.json())

    print("\n[Test 4] Testing POST /flag with JSON body (Flutter ON: flag=1)...")
    res = client.post("/flag", json={"flag": 1}, headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == {"flag": 1, "status": "ok"}
    assert get_flag() == 1
    print("  -> Passed! Response: ", res.json())

    print("\n[Test 5] Testing POST /flag with JSON body (Flutter OFF: flag=0)...")
    res = client.post("/flag", json={"flag": 0}, headers=AUTH_HEADERS)
    assert res.status_code == 200
    assert res.json() == {"flag": 0, "status": "ok"}
    assert get_flag() == 0
    print("  -> Passed! Response: ", res.json())

    print("\n[Test 6] Testing Query Param API Key (?api_key=...)...")
    res = client.get(f"/flag?flag=1&api_key={API_KEY_ENV}")
    assert res.status_code == 200
    assert res.json() == {"flag": 1, "status": "ok"}
    assert get_flag() == 1

    res = client.get(f"/flag?flag=0&api_key={API_KEY_ENV}")
    assert res.status_code == 200
    assert res.json() == {"flag": 0, "status": "ok"}
    assert get_flag() == 0
    print("  -> Passed! Query param auth works.")

    print("\n[Test 7] Testing Shortcut endpoints /on and /off...")
    res = client.post("/on", headers=AUTH_HEADERS)
    assert res.json() == {"flag": 1, "status": "ok"}
    assert get_flag() == 1

    res = client.post("/off", headers=AUTH_HEADERS)
    assert res.json() == {"flag": 0, "status": "ok"}
    assert get_flag() == 0
    print("  -> Passed! Shortcut endpoints working.")

    print("\n[Test 8] Testing Flag Guard on submit_attendance when flag == 0...")
    set_flag(0)
    success, status, data = submit_attendance.run_pipeline(student_id="test123")
    assert success is False
    assert status == "FLAG_DISABLED"
    print("  -> Passed! Execution was safely aborted without calling link_generator.")


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING BACKEND AUTH & FLUTTER TESTS")
    print("=" * 60)
    test_flag_lifecycle()
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED WITH API KEY AUTHENTICATION!")
    print("=" * 60)
