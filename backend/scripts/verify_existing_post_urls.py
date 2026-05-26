"""Clear existing post URLs that do not verify against saved post content."""

import sqlite3
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from core.security import reveal_text  # noqa: E402
from services.linkedin_browser_post_service import import_selenium, make_driver, seed_linkedin_cookies, verify_exact_post_url  # noqa: E402


def main():
    conn = sqlite3.connect(BACKEND_DIR / "data" / "hiremate.db")
    conn.row_factory = sqlite3.Row
    user = dict(conn.execute("SELECT * FROM users ORDER BY id DESC LIMIT 1").fetchone())
    rows = conn.execute(
        """
        SELECT id, post_url, post_text
        FROM leads
        WHERE lead_kind='post'
          AND post_url LIKE 'https://www.linkedin.com/feed/update/%'
        ORDER BY id DESC
        LIMIT 40
        """
    ).fetchall()
    user["linkedin_cookie"] = reveal_text(user.get("linkedin_cookie_cipher") or "")
    webdriver, by, _wait, _ec, options = import_selenium()
    driver = make_driver(webdriver, options, user)
    checked = 0
    cleared = 0
    try:
        seed_linkedin_cookies(driver, user["linkedin_cookie"])
        for row in rows:
            checked += 1
            if not verify_exact_post_url(driver, by, row["post_url"], row["post_text"] or ""):
                conn.execute("UPDATE leads SET post_url='' WHERE id=?", (row["id"],))
                cleared += 1
        conn.commit()
    finally:
        driver.quit()
        conn.close()
    print(f"checked {checked}; cleared {cleared}")


if __name__ == "__main__":
    main()
