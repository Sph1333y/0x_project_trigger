"""
flag_manager.py
================
Thread-safe and atomic manager for reading and updating flag_data.json.

Guarantees:
  - If flag_data.json does not exist, it initializes with {"flag": 0}.
  - Safe concurrent read/write access via threading.Lock.
  - Returns integer flag value (0 or 1).
  - Validates flag value strictly (only 0 or 1 allowed).
"""

import os
import json
import threading
from datetime import datetime, timezone
from typing import Literal

FLAG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flag_data.json")
_lock = threading.Lock()


def get_flag() -> Literal[0, 1]:
    """
    Reads the current flag from flag_data.json.
    Returns:
        1 if flag is ON
        0 if flag is OFF (or on file read error / missing file / invalid content)
    """
    with _lock:
        if not os.path.exists(FLAG_FILE_PATH):
            _initialize_default()
            return 0

        try:
            with open(FLAG_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                val = data.get("flag", 0)
                return 1 if val == 1 else 0
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            return 0


def set_flag(value: Literal[0, 1]) -> Literal[0, 1]:
    """
    Updates flag_data.json with the given flag value (1 or 0).
    Raises ValueError if value is not 0 or 1.
    Returns:
        The updated flag value (0 or 1).
    """
    if value not in (0, 1):
        raise ValueError(f"Invalid flag value: {value}. Flag must be strictly 0 or 1.")

    with _lock:
        data = {
            "flag": value,
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
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    return value


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
