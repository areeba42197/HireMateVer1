from core.database import db, rows_to_dicts
from services.ai_draft_service import generate_ai_draft


def generate_draft(user_id, lead, draft_type="message", tone="professional"):
    """Generate an AI draft and save it as an editable pending draft."""
    tone_key = (tone or "professional").lower()
    draft_type = "comment" if draft_type == "comment" else "message"
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            raise RuntimeError("User profile was not found.")
        ai_payload = generate_ai_draft(dict(user), lead, draft_type=draft_type, tone=tone_key)
        content_key = "message_draft" if draft_type == "message" else "comment_draft"
        content = ai_payload[content_key]
        existing = conn.execute(
            """
            SELECT id FROM drafts
            WHERE user_id=? AND lead_id=? AND draft_type=?
            ORDER BY updated_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (user_id, lead["id"], draft_type),
        ).fetchone()
        if existing:
            draft_id = existing["id"]
            conn.execute(
                """
                UPDATE drafts
                SET tone=?, content=?, status='pending', updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND user_id=?
                """,
                (tone_key, content, draft_id, user_id),
            )
            conn.execute(
                "DELETE FROM drafts WHERE user_id=? AND lead_id=? AND draft_type=? AND id<>?",
                (user_id, lead["id"], draft_type, draft_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO drafts(user_id, lead_id, draft_type, tone, content) VALUES (?, ?, ?, ?, ?)",
                (user_id, lead["id"], draft_type, tone_key, content),
            )
            draft_id = cur.lastrowid
        conn.execute(
            "INSERT INTO events(user_id, event_type, details) VALUES (?, ?, ?)",
            (user_id, "draft_generated", f"{draft_type}:{tone_key}:ai"),
        )
        row = conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        draft = dict(row)
        draft["ai"] = ai_payload
        return draft


def list_drafts(user_id):
    with db() as conn:
        compact_duplicate_drafts(conn, user_id)
        rows = conn.execute(
            """
            SELECT d.*, l.company, l.role_title, l.temperature
            FROM drafts d
            JOIN leads l ON l.id=d.lead_id
            WHERE d.user_id=?
            ORDER BY d.created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return rows_to_dicts(rows)


def compact_duplicate_drafts(conn, user_id):
    rows = conn.execute(
        """
        SELECT id, lead_id, draft_type
        FROM drafts
        WHERE user_id=?
        ORDER BY lead_id, draft_type, updated_at DESC, created_at DESC, id DESC
        """,
        (user_id,),
    ).fetchall()
    seen = set()
    delete_ids = []
    for row in rows:
        key = (row["lead_id"], row["draft_type"])
        if key in seen:
            delete_ids.append(row["id"])
        else:
            seen.add(key)
    if delete_ids:
        conn.execute(
            "DELETE FROM drafts WHERE user_id=? AND id IN (" + ",".join(["?"] * len(delete_ids)) + ")",
            [user_id] + delete_ids,
        )


def get_draft(user_id, draft_id):
    """Return one draft with its lead context for the review page."""
    with db() as conn:
        row = conn.execute(
            """
            SELECT d.*, l.company, l.role_title, l.temperature, l.post_url, l.lead_kind,
                   l.post_text, l.author_name, l.author_title, l.location, l.work_type
            FROM drafts d
            JOIN leads l ON l.id=d.lead_id
            WHERE d.user_id=? AND d.id=?
            """,
            (user_id, draft_id),
        ).fetchone()
        return dict(row) if row else None


def update_draft_status(user_id, draft_id, status, content=None):
    with db() as conn:
        if content is not None:
            conn.execute("UPDATE drafts SET status=?, content=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", (status, content, draft_id, user_id))
        else:
            conn.execute("UPDATE drafts SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", (status, draft_id, user_id))
        conn.execute("INSERT INTO events(user_id, event_type, details) VALUES (?, ?, ?)", (user_id, "draft_status", f"{draft_id}:{status}"))
        row = conn.execute("SELECT * FROM drafts WHERE id=? AND user_id=?", (draft_id, user_id)).fetchone()
        return dict(row) if row else None


def delete_draft(user_id, draft_id):
    with db() as conn:
        cur = conn.execute("DELETE FROM drafts WHERE id=? AND user_id=?", (draft_id, user_id))
        if cur.rowcount:
            conn.execute("INSERT INTO events(user_id, event_type, details) VALUES (?, ?, ?)", (user_id, "draft_deleted", str(draft_id)))
        return cur.rowcount > 0
