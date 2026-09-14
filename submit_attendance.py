"""
submit_attendance.py (Cloud-Ready / Stateless)
==============================================
Submits student attendance in a cloud environment (AWS EC2 ARM64, Ubuntu Linux)
with ZERO persistent profiles, ZERO stored cookies, and ZERO local system data.

Process Architecture:
  1. Checks flag_data.json via flag_manager. If flag != 1, aborts immediately.
  2. Calls link_generator.py to get the active token and link.
  3. Launches a clean, stateless headless browser (no chrome_profile).
  4. Fills in the student ID and submits the form.
  5. Evaluates response against True / False states:
     TRUE STATES (Stops attempt and succeeds):
       1) 'Attendance successfully recorded for' (green tag - True)
       2) 'Attendance already recorded' (red tag - True because already marked)
     FALSE STATES (Restarts from step 1: link_generator):
       1) 'QR Code Expired. Please scan latest QR' (red tag - False)
       2) Any other error or unexpected message (False)
"""

import sys
import os
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from link_generator import get_attendance_link
from flag_manager import get_flag

logger = logging.getLogger("submit_attendance")

MAX_RETRIES = 5
RETRY_DELAY = 3  # seconds between retries


def create_cloud_driver():
    """
    Initializes a completely stateless Chromium/Chrome browser suitable for
    cloud runners (e.g., AWS EC2 ARM64 Ubuntu with Chromium).
    No user-data directory, no stored cookies, no persistence on disk.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # Standard generic desktop user-agent for cloud environments
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver


def submit_to_page(driver, attendance_url: str, student_id: str):
    """
    Navigates to the generated attendance page, inputs student ID,
    clicks Submit Attendance, and returns the response HTML from #msg.
    """
    logger.info(f"[submit_attendance] Loading attendance page: {attendance_url}")
    driver.get(attendance_url)

    # Google Apps Script renders inside nested iframes
    wait = WebDriverWait(driver, 15)
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "sandboxFrame")))
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "userHtmlFrame")))

    # Fill student ID
    student_input = wait.until(EC.presence_of_element_located((By.ID, "studentid")))
    student_input.clear()
    student_input.send_keys(student_id)
    logger.info(f"[submit_attendance] Entered student ID: {student_id}")

    # Click Submit Attendance button
    submit_btn = driver.find_element(By.TAG_NAME, "button")
    submit_btn.click()
    logger.info("[submit_attendance] Clicked 'Submit Attendance'")

    # Wait for server response in <div id="msg">
    msg_elem = wait.until(EC.presence_of_element_located((By.ID, "msg")))
    for _ in range(25):
        time.sleep(1)
        resp_text = msg_elem.get_attribute("innerHTML") or ""
        if resp_text.strip():
            return resp_text.strip()

    return None


def run_pipeline(student_id: str = "test123", max_retries: int = MAX_RETRIES):
    """
    Executes the full pipeline with auto-recovery from step 1 on failure.
    Enforces Flag Guard: Only runs when flag == 1 in flag_data.json.
    """
    # ── Pre-flight Flag Guard ────────────────────────────────────────
    current_flag = get_flag()
    logger.info(f"[FLAG CHECK] Checking flag_data.json: flag = {current_flag}")
    if current_flag != 1:
        logger.info("[FLAG GUARD] Flag is 0 (OFF). Execution ABORTED.")
        return False, "FLAG_DISABLED", "Flag is 0 (OFF). Execution aborted."

    for attempt in range(1, max_retries + 1):
        # Re-check flag before each attempt in case it was toggled OFF
        if get_flag() != 1:
            logger.info("[FLAG GUARD] Flag was switched to 0 (OFF). Stopping further attempts.")
            return False, "FLAG_DISABLED", "Flag switched to OFF during retries."

        logger.info(f"[CLOUD RUN] ATTEMPT {attempt}/{max_retries} | Student: {student_id}")

        # ── Step 1: Generate Link ────────────────────────────────────────
        logger.info("[Step 1] Requesting live attendance link via link_generator...")
        token, link = get_attendance_link()

        if not token or not link:
            logger.warning("[Step 1] [FAIL] Could not retrieve token. Retrying from start...")
            time.sleep(RETRY_DELAY)
            continue

        logger.info(f"[Step 1] [OK] Live Token: {token}")

        # ── Step 2: Submit Attendance (Stateless Browser) ────────────────
        driver = None
        try:
            logger.info("[Step 2] Initializing stateless cloud browser...")
            driver = create_cloud_driver()

            response = submit_to_page(driver, link, student_id)
            logger.info(f"[Step 2] Server response received: {response}")

            if not response:
                logger.warning("[Step 2] [FAIL] No response from server. Restarting from Step 1...")
                continue

            # ── Step 3: Parse Result (True / False States) ───────────────
            resp_lower = response.lower()

            # ── TRUE STATES (Stop attempt and mark SUCCESS) ───────────────
            # True State 1: "Attendance successfully recorded for" (green tag)
            if "successfully recorded" in resp_lower or "attendance successfully recorded" in resp_lower:
                logger.info("[TRUE STATE 1] Attendance successfully recorded!")
                return True, "ATTENDANCE_SUCCESSFULLY_RECORDED", response

            # True State 2: "Attendance already recorded" (red tag, but considered TRUE)
            if "already recorded" in resp_lower or "attendance already recorded" in resp_lower or "already marked" in resp_lower:
                logger.info("[TRUE STATE 2] Attendance already recorded! (Recorded previously)")
                return True, "ATTENDANCE_ALREADY_RECORDED", response

            # ── FALSE STATES (Retry from the start: link_generator) ──────
            # False State 1: "QR Code Expired. Please scan latest QR"
            if "expired" in resp_lower or "scan latest" in resp_lower:
                logger.warning(f"[FALSE STATE 1] QR Code Expired: {response.strip()}")
                logger.info("--> Action: Restarting from the beginning (link_generator)...")
                continue

            # False State 2: Any other error or unexpected message
            logger.warning(f"[FALSE STATE 2] Error / Unexpected message: {response.strip()}")
            logger.info("--> Action: Restarting from the beginning (link_generator)...")
            continue

        except Exception as exc:
            logger.error(f"[ERROR] Exception occurred during submission: {exc}")
            continue

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            if attempt < max_retries:
                time.sleep(RETRY_DELAY)

    logger.error(f"[FAILED] Pipeline failed after {max_retries} attempts.")
    return False, "MAX_RETRIES_EXCEEDED", None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    student_id = "test123"
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        student_id = sys.argv[1]

    print(">> Starting Cloud Attendance Runner (Stateless)")
    print(f"   Student ID  : {student_id}")
    print(f"   Max Retries : {MAX_RETRIES}")

    success, status, data = run_pipeline(student_id=student_id)

    if status == "FLAG_DISABLED":
        print("\nProcess halted: Flag is 0 (OFF). No actions were taken.")
        sys.exit(0)
    elif success:
        print("\nProcess finished with success!")
        sys.exit(0)
    else:
        print("\nProcess failed.")
        sys.exit(1)
