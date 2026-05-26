"""Test post collection for the user with the latest saved LinkedIn cookie.

This script does not print or expose the cookie. It only reports which user was
tested, which keyword batch was used, and whether LinkedIn returned posts.
"""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.database import db
from core.security import reveal_text
from services.linkedin_post_service import collect_posts_for_profile
from services.public_post_search_service import collect_public_linkedin_posts


def email_hint(email):
    if "@" not in email:
        return "hidden"
    name, domain = email.split("@", 1)
    return f"{name[:2]}***{domain}"


def latest_cookie_user():
    with db() as conn:
        latest = conn.execute(
            """
            SELECT user_id, event_type, created_at
            FROM events
            WHERE event_type='linkedin_cookie_updated'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        if latest:
            user = conn.execute("SELECT * FROM users WHERE id=?", (latest["user_id"],)).fetchone()
        else:
            user = conn.execute(
                """
                SELECT * FROM users
                WHERE linkedin_cookie_cipher IS NOT NULL
                  AND linkedin_cookie_cipher <> ''
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        return (dict(user) if user else None), (dict(latest) if latest else None)


def main():
    user, event = latest_cookie_user()
    if not user:
        print(json.dumps({"ok": False, "message": "No saved LinkedIn cookie found."}, indent=2))
        return

    cipher = user.get("linkedin_cookie_cipher") or ""
    user["linkedin_cookie"] = reveal_text(cipher) if cipher else ""

    posts, errors = collect_posts_for_profile(user, keyword_offset=0)
    source = "linkedin-session"
    if not posts:
        public_posts, public_errors = collect_public_linkedin_posts(user, keyword_offset=0)
        posts = public_posts
        errors.extend(public_errors)
        source = "public-index"

    print(
        json.dumps(
            {
                "ok": True,
                "tested_user_id": user["id"],
                "tested_email_hint": email_hint(user.get("email", "")),
                "latest_cookie_event": event,
                "source": source,
                "importable_posts": len(posts),
                "errors": errors[:6],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
