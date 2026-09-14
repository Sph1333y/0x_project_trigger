"""
link_generator.py (Cloud-Ready / Stateless)
===========================================
Extracts the live rotating attendance token from the public display page
using pure HTTP requests. Requires zero cookies, zero profiles, and zero
system/device data.

Usage:
  # Standalone:
  python link_generator.py

  # Module import:
  from link_generator import get_attendance_link
  token, link = get_attendance_link()
"""

import sys
import os
import re
import html
import logging
import requests

logger = logging.getLogger("link_generator")

BASE_URL = (
    "https://script.google.com/macros/s/"
    "AKfycby2RWaYHWIIVGeN07CczwRnoP7Tjoe5_1ETRhdQKXtCiPXpNCYRPzSVSUSxn0XozerMBw"
    "/exec"
)

# Configurable venue via ATTENDANCE_VENUE environment variable (default: G4104)
DEFAULT_VENUE = os.getenv("ATTENDANCE_VENUE", "G4104")

# Standard generic User-Agent for cloud environments
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def extract_token_from_html(html_content: str):
    """Parses 6-character token from Google Apps Script HTML response."""
    if not html_content:
        return None

    # Pattern 1: JSON payload inside goog.script.init("...")
    match = re.search(r'goog\.script\.init\("([^"]+)"', html_content)
    if match:
        decoded = html.unescape(html.unescape(match.group(1)))
        token_match = re.search(r"Current Token\s*:\s*([A-Z0-9]+)", decoded)
        if token_match:
            return token_match.group(1)

    # Pattern 2: Raw HTML text
    token_match = re.search(r"Current Token\s*:\s*([A-Z0-9]+)", html_content)
    if token_match:
        return token_match.group(1)

    return None


def get_attendance_link(venue: str = None, timeout: int = 15):
    """
    Fetches the live rotating token and generates the attendance link.
    Returns:
        (token, link) on success
        (None, None) on failure
    """
    selected_venue = venue or os.getenv("ATTENDANCE_VENUE", DEFAULT_VENUE)
    url = f"{BASE_URL}?display=1&v={selected_venue}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()

        if "too many scripts running simultaneously" in response.text:
            logger.warning("[link_generator] Server temporarily rate-limited.")
            return None, None

        token = extract_token_from_html(response.text)
        if token:
            link = f"{BASE_URL}?v={selected_venue}&t={token}"
            return token, link

    except requests.RequestException as exc:
        logger.error(f"[link_generator] Network request error: {exc}")

    return None, None


if __name__ == "__main__":
    print("[link_generator] Fetching current attendance link...")
    token, link = get_attendance_link()

    if not token or not link:
        print("[link_generator] [ERROR] Failed to fetch token.")
        sys.exit(1)

    print(f"Token: {token}")
    print(f"Link : {link}")
