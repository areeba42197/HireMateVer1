"""Check which author activity URL variant exposes exact post links."""

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
    row = conn.execute(
        """
        SELECT reactions_json
        FROM leads
        WHERE lead_kind='post' AND coalesce(post_url, '')='' AND reactions_json LIKE '%author_profile_url%'
        ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    conn.close()
    reaction = json.loads(row["reactions_json"] or "{}") if row else {}
    profile = reaction.get("author_profile_url", "")
    user["linkedin_cookie"] = reveal_text(user.get("linkedin_cookie_cipher") or "")
    webdriver, by, _wait, _ec, options = import_selenium()
    driver = make_driver(webdriver, options, user)
    out = []
    try:
        seed_linkedin_cookies(driver, user["linkedin_cookie"])
        for suffix in ["/recent-activity/all/", "/recent-activity/posts/", "/detail/recent-activity/"]:
            url = profile.rstrip("/") + suffix
            driver.get(url)
            time.sleep(5)
            hrefs = []
            for anchor in driver.find_elements(by.CSS_SELECTOR, "a"):
                href = (anchor.get_attribute("href") or "").split("?")[0]
                if "feed/update" in href or "urn:li:activity" in href or "/posts/" in href:
                    if href not in hrefs:
                        hrefs.append(href)
            activity_ids = sorted(set(re.findall(r"urn:li:activity:(\d+)", driver.page_source or "")))[:10]
            out.append({"url": url, "title": driver.title, "hrefs": hrefs[:10], "activity_ids": activity_ids, "body": driver.find_element(by.TAG_NAME, "body").text[:500]})
        print(json.dumps(out, ensure_ascii=True))
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
