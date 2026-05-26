import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.database import db, init_db
from services.lead_service import import_posts, sample_posts


def main():
    init_db()
    with db() as conn:
        user = conn.execute("SELECT id, email FROM users ORDER BY id LIMIT 1").fetchone()
        if not user:
            raise SystemExit("No user found. Start the backend once or register a user first.")
        user_id = user["id"]
        email = user["email"]
    imported = import_posts(user_id, sample_posts())
    print(f"Imported {len(imported)} sample LinkedIn-style posts for {email}.")


if __name__ == "__main__":
    main()
