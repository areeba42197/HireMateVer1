"""Print recent post reaction metadata for scraper verification."""

import json
import sqlite3
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def main():
    conn = sqlite3.connect(BACKEND_DIR / "data" / "hiremate.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, company, post_url, reactions_json
        FROM leads
        WHERE lead_kind='post'
        ORDER BY id DESC
        LIMIT 8
        """
    ).fetchall()
    data = []
    for row in rows:
        try:
            reaction = json.loads(row["reactions_json"] or "{}")
        except json.JSONDecodeError:
            reaction = {}
        data.append(
            {
                "id": row["id"],
                "company": row["company"],
                "post_url": row["post_url"],
                "author_profile_url": reaction.get("author_profile_url", ""),
                "query": reaction.get("query", ""),
            }
        )
    print(json.dumps(data, ensure_ascii=True))
    conn.close()


if __name__ == "__main__":
    main()
