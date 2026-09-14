"""
flag_manager.py
================
Thread-safe and atomic manager for reading and updating flag_data.json.

Guarantees:
  - If flag_data.json does not exist, it initializes with {"flag": 0}.
  - Safe concurrent read/write access.
  - Returns integer flag value (0 or 1).
"""

import os
import json
import threading
from datetime import datetime, timezone

FLAG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flag_data.json")
_lock = threading.Lock()


def get_flag() -> int:
    """
    Reads the current flag from flag_data.json.
    Returns:
        1 if flag is ON
        0 if flag is OFF (or on file read error / missing file)
    """
    with _lock:
        if not os.path.exists(FLAG_FILE_PATH):
            _initialize_default()
            return 0

        try:
            with open(FLAG_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return int(data.get("flag", 0))
        except (json.JSONDecodeError, OSError, ValueError):
            return 0


def set_flag(value: int) -> int:
    """
    Updates flag_data.json with the given flag value (1 or 0).
    Returns:
        The updated flag value (0 or 1).
    """
    clean_val = 1 if int(value) == 1 else 0

    with _lock:
        data = {
            "flag": clean_val,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        temp_path = f"{FLAG_FILE_PATH}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, FLAG_FILE_PATH)
        except OSError:
            # Fallback direct write if atomic replace fails
            with open(FLAG_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

    return clean_val


def _initialize_default():
    """Helper to initialize flag_data.json if missing."""
    data = {
        "flag": 0,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    with open(FLAG_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    current = get_flag()
    print(f"[flag_manager] Current flag: {current}")
