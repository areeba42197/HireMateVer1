"""Backfill a LinkedIn search fallback URL for post leads missing direct URLs."""

import json
import sqlite3
from pathlib import Path
from urllib.parse import quote_plus


BACKEND_DIR = Path(__file__).resolve().parents[1]


def main():
    conn = sqlite3.connect(BACKEND_DIR / "data" / "hiremate.db")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, role_title, author_name, reactions_json
        FROM leads
        WHERE lead_kind='post'
          AND coalesce(post_url, '')=''
        """
    ).fetchall()
    updated = 0
    for row in rows:
        try:
            reaction = json.loads(row["reactions_json"] or "{}")
        except json.JSONDecodeError:
            reaction = {}
        if reaction.get("source_search_url"):
            continue
        query = reaction.get("query") or " ".join(part for part in [row["author_name"], row["role_title"]] if part)
        if not query:
            continue
        reaction["source_search_url"] = (
            "https://www.linkedin.com/search/results/content/?keywords="
            + quote_plus(query)
            + "&origin=GLOBAL_SEARCH_HEADER"
        )
        conn.execute(
            "UPDATE leads SET reactions_json=? WHERE id=?",
            (json.dumps(reaction, ensure_ascii=False), row["id"]),
        )
        updated += 1
    conn.commit()
    conn.close()
    print(f"updated {updated}")


if __name__ == "__main__":
    main()
