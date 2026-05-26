"""Best-effort exact LinkedIn post URL backfill for recent post leads."""

import json
import sqlite3
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from core.security import reveal_text  # noqa: E402
from services.linkedin_browser_post_service import (  # noqa: E402
    import_selenium,
    make_driver,
    resolve_post_url_from_author_activity,
    seed_linkedin_cookies,
)


def main():
    conn = sqlite3.connect(BACKEND_DIR / "data" / "hiremate.db")
    conn.row_factory = sqlite3.Row
    user = dict(conn.execute("SELECT * FROM users ORDER BY id DESC LIMIT 1").fetchone())
    rows = conn.execute(
        """
        SELECT id, post_text, reactions_json
        FROM leads
        WHERE lead_kind='post'
          AND coalesce(post_url, '')=''
          AND reactions_json LIKE '%author_profile_url%'
        ORDER BY id DESC
        LIMIT 12
        """
    ).fetchall()
    user["linkedin_cookie"] = reveal_text(user.get("linkedin_cookie_cipher") or "")
    webdriver, by, _wait, _ec, options = import_selenium()
    driver = make_driver(webdriver, options, user)
    updated = 0
    try:
        seed_linkedin_cookies(driver, user["linkedin_cookie"])
        for row in rows:
            try:
                reaction = json.loads(row["reactions_json"] or "{}")
            except json.JSONDecodeError:
                reaction = {}
            author_url = reaction.get("author_profile_url", "")
            exact_url = resolve_post_url_from_author_activity(driver, by, author_url, row["post_text"] or "")
            if exact_url:
                conn.execute("UPDATE leads SET post_url=? WHERE id=?", (exact_url, row["id"]))
                updated += 1
        conn.commit()
    finally:
        driver.quit()
        conn.close()
    print(f"updated {updated} of {len(rows)}")


if __name__ == "__main__":
    main()
