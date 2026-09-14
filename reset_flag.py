"""
reset_flag.py
=============
Utility script to quickly reset the flag to 0 (OFF) in flag_data.json.

Guarantees:
  - Uses thread-safe and atomic file write via flag_manager.
  - Returns exit code 0 on successful reset.
  - Can be executed directly from terminal or scheduled via cron/tasks.

Usage:
  python reset_flag.py
"""

import sys
from flag_manager import set_flag, get_flag, FLAG_FILE_PATH


def reset_flag():
    """Sets flag to 0 in flag_data.json and prints status."""
    previous_value = get_flag()
    print(f"[reset_flag] Previous flag state : {previous_value}")
    
    new_value = set_flag(0)
    print(f"[reset_flag] Updated flag state  : {new_value}")
    print(f"[reset_flag] Target file         : {FLAG_FILE_PATH}")
    print("[reset_flag] [SUCCESS] Flag has been safely reset to 0 (OFF).")
    return new_value


if __name__ == "__main__":
    try:
        reset_flag()
        sys.exit(0)
    except Exception as e:
        print(f"[reset_flag] [ERROR] Failed to reset flag: {e}")
        sys.exit(1)
