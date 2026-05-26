"""Print non-sensitive diagnostics for LinkedIn's rendered content search page."""

import re
import sqlite3
import sys
import time
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from core.security import reveal_text  # noqa: E402
from services.linkedin_browser_post_service import import_selenium, make_driver, seed_linkedin_cookies  # noqa: E402


def main():
    conn = sqlite3.connect(BACKEND_DIR / "data" / "hiremate.db")
    conn.row_factory = sqlite3.Row
    user = dict(conn.execute("SELECT * FROM users ORDER BY id DESC LIMIT 1").fetchone())
    conn.close()
    user["linkedin_cookie"] = reveal_text(user.get("linkedin_cookie_cipher") or "")
    webdriver, by, _wait, _ec, options = import_selenium()
    driver = make_driver(webdriver, options, user)
    try:
        seed_linkedin_cookies(driver, user["linkedin_cookie"])
        driver.get("https://www.linkedin.com/search/results/content/?keywords=Python%20developer&origin=GLOBAL_SEARCH_HEADER")
        time.sleep(8)
        html = driver.page_source or ""
        classes = sorted(set(re.findall(r'class="([^"]+)"', html)))
        hits = [
            item
            for item in classes
            if any(token in item.lower() for token in ["search", "update", "feed", "entity", "result", "reusable"])
        ][:60]
        body = driver.find_element(by.TAG_NAME, "body").text[:1200]
        print("TITLE:", driver.title)
        print("URL:", driver.current_url[:180])
        print("CLASS_HINTS:", hits)
        print("BODY:", body.encode("ascii", "ignore").decode())
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
