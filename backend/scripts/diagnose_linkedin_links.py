"""Inspect non-sensitive LinkedIn links exposed on the rendered content page."""

import json
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
        driver.get("https://www.linkedin.com/search/results/content/?keywords=LLM%20hiring&origin=GLOBAL_SEARCH_HEADER")
        time.sleep(8)
        hrefs = []
        for anchor in driver.find_elements(by.CSS_SELECTOR, "a"):
            href = (anchor.get_attribute("href") or "").split("?")[0]
            text = (anchor.text or "").replace("\n", " ").strip()[:90]
            if any(token in href for token in ["feed/update", "activity", "/posts/", "linkedin.com/in/"]):
                hrefs.append({"href": href, "text": text})
        activity_ids = sorted(set(re.findall(r"urn:li:activity:(\d+)", driver.page_source or "")))
        print(json.dumps({"hrefs": hrefs[:80], "activity_ids": activity_ids[:20]}, ensure_ascii=True))
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
