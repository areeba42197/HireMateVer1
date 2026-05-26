"""Refresh existing LinkedIn post rows with the current post analyzer."""

import sqlite3
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from services.post_analysis_service import analyze_post_text, is_generic_author, is_generic_role  # noqa: E402


def merge_tags(existing, analyzed):
    tags = []
    for item in list((existing or "").split(",")) + list(analyzed or []):
        tag = item.strip()
        if tag and tag not in tags:
            tags.append(tag)
    return ", ".join(tags)


def main():
    db_path = BACKEND_DIR / "data" / "hiremate.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, company, role_title, author_name, post_text, tags
        FROM leads
        WHERE lead_kind='post'
          AND post_url LIKE '%linkedin.com/%'
        """
    ).fetchall()
    changed = 0
    for row in rows:
        analysis = analyze_post_text(
            row["post_text"] or "",
            row["author_name"] or row["company"] or "",
            row["role_title"] or "",
        )
        company = row["company"] or analysis["company"]
        role_title = row["role_title"] or analysis["role_title"]
        if is_generic_author(company):
            company = analysis["company"] or company
        if is_generic_role(role_title):
            role_title = analysis["role_title"] or role_title
        tags = merge_tags(row["tags"], analysis["tags"])
        if company != row["company"] or role_title != row["role_title"] or tags != (row["tags"] or ""):
            conn.execute(
                "UPDATE leads SET company=?, role_title=?, tags=? WHERE id=?",
                (company, role_title, tags, row["id"]),
            )
            changed += 1
    conn.commit()
    conn.close()
    print(f"Analyzed {len(rows)} LinkedIn post rows; updated {changed}.")


if __name__ == "__main__":
    main()
