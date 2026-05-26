"""Print latest imported post leads for quick local verification."""

import json
import sqlite3
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def main():
    conn = sqlite3.connect(BACKEND_DIR / "data" / "hiremate.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, company, role_title, substr(post_text, 1, 90) AS text_preview
        FROM leads
        WHERE lead_kind='post'
        ORDER BY datetime(created_at) DESC
        LIMIT 8
        """
    ).fetchall()
    print(json.dumps([dict(row) for row in rows], ensure_ascii=True))
    conn.close()


if __name__ == "__main__":
    main()
