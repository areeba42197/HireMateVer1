"""Run the browser-rendered LinkedIn post fallback for the latest cookie user."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.database import db
from core.security import reveal_text
from services.linkedin_browser_post_service import collect_posts_with_browser


def main():
    with db() as conn:
        event = conn.execute(
            "SELECT user_id FROM events WHERE event_type='linkedin_cookie_updated' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        user_id = event["user_id"] if event else 4
        user = dict(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())

    user["linkedin_cookie"] = reveal_text(user.get("linkedin_cookie_cipher") or "")
    posts, errors = collect_posts_with_browser(user, keyword_offset=0, max_posts=8, scrolls=5, exact_link_limit=8)
    print(
        json.dumps(
            {
                "user_id": user["id"],
                "posts": len(posts),
                "first": posts[0] if posts else None,
                "errors": errors[:8],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
