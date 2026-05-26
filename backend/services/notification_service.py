"""User email notifications for HireMate.

This module checks saved notification preferences before sending email. It also
records every send attempt in SQLite so the project has an audit trail.
"""

from datetime import datetime, timedelta, timezone
import html
import json

from core.database import db
from services.email_service import email_is_configured, send_email


PK_TZ = timezone(timedelta(hours=5))


def get_preferences(conn, user_id):
    row = conn.execute("SELECT * FROM notification_preferences WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        conn.execute("INSERT INTO notification_preferences(user_id) VALUES (?)", (user_id,))
        row = conn.execute("SELECT * FROM notification_preferences WHERE user_id=?", (user_id,)).fetchone()
    return row


def log_email(user_id, notification_type, recipient, subject, status, error_text=""):
    with db() as conn:
        conn.execute(
            """
            INSERT INTO email_notifications(user_id, notification_type, recipient_email, subject, status, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, notification_type, recipient, subject, status, error_text[:500]),
        )


def deliver(user, notification_type, subject, text_body, html_body=None):
    """Send an email and record success/failure for admin/debugging."""
    recipient = user.get("email", "")
    try:
        result = send_email(recipient, subject, text_body, html_body)
        log_email(user.get("id"), notification_type, recipient, subject, "sent")
        return result
    except Exception as exc:
        log_email(user.get("id"), notification_type, recipient, subject, "failed", str(exc))
        raise


def send_test_email(user):
    subject = "HireMate email notifications are ready"
    text = (
        f"Hi {user.get('first_name', 'there')},\n\n"
        "This is a test email from HireMate. Your notification email setup is working.\n\n"
        "HireMate"
    )
    html_body = email_shell(
        "Email notifications are ready",
        f"Hi {html.escape(user.get('first_name') or 'there')}, your HireMate email notification setup is working.",
    )
    return deliver(user, "test_email", subject, text, html_body)


def notify_draft_approved(user_id, draft):
    with db() as conn:
        user = dict(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
        prefs = get_preferences(conn, user_id)
        if not prefs["draft_confirmations"]:
            return {"skipped": True, "reason": "draft confirmations disabled"}

    subject = "Your HireMate draft was approved"
    text = (
        f"Hi {user.get('first_name', 'there')},\n\n"
        f"Your {draft.get('draft_type', 'draft')} draft for {draft.get('company', 'a lead')} "
        f"({draft.get('role_title', 'opportunity')}) was approved and saved.\n\n"
        "You can review it from the Drafts section in HireMate.\n\nHireMate"
    )
    html_body = email_shell(
        "Draft approved",
        (
            f"Your <strong>{html.escape(draft.get('draft_type', 'draft'))}</strong> draft for "
            f"<strong>{html.escape(draft.get('company', 'a lead'))}</strong> was approved and saved."
        ),
    )
    return deliver(user, "draft_approved", subject, text, html_body)


def notify_hot_leads(user, leads):
    hot = [lead for lead in leads or [] if lead.get("temperature") == "hot"]
    if not hot:
        return {"skipped": True, "reason": "no hot leads"}
    with db() as conn:
        prefs = get_preferences(conn, user["id"])
        if not prefs["hot_lead_alerts"]:
            return {"skipped": True, "reason": "hot lead alerts disabled"}

    first = hot[0]
    subject = f"{len(hot)} new hot lead{'s' if len(hot) != 1 else ''} found by HireMate"
    text = (
        f"Hi {user.get('first_name', 'there')},\n\n"
        f"HireMate found {len(hot)} new hot lead(s). Top match: "
        f"{first.get('company', 'Company')} - {first.get('role_title', 'Opportunity')}.\n\n"
        "Open HireMate to review and generate your draft.\n\nHireMate"
    )
    rows = "".join(
        f"<li><strong>{html.escape(lead.get('company', 'Company'))}</strong> - "
        f"{html.escape(lead.get('role_title', 'Opportunity'))}</li>"
        for lead in hot[:5]
    )
    html_body = email_shell("New hot leads found", f"<p>HireMate found {len(hot)} hot lead(s):</p><ul>{rows}</ul>")
    return deliver(user, "hot_lead_alert", subject, text, html_body)


def maybe_send_daily_summary(user):
    with db() as conn:
        prefs = get_preferences(conn, user["id"])
        if not prefs["daily_summary"]:
            return {"skipped": True, "reason": "daily summary disabled"}
        today = datetime.now(PK_TZ).date().isoformat()
        if str(prefs["last_daily_summary_at"] or "").startswith(today):
            return {"skipped": True, "reason": "already sent today"}

        counts = conn.execute(
            """
            SELECT
              COUNT(*) total,
              SUM(CASE WHEN temperature='hot' THEN 1 ELSE 0 END) hot,
              SUM(CASE WHEN status='saved' THEN 1 ELSE 0 END) saved
            FROM leads
            WHERE user_id=? AND datetime(created_at) >= datetime('now', '-1 day')
            """,
            (user["id"],),
        ).fetchone()
        drafts = conn.execute(
            "SELECT COUNT(*) pending FROM drafts WHERE user_id=? AND status='pending'",
            (user["id"],),
        ).fetchone()

    subject = "Your HireMate daily summary"
    text = (
        f"Hi {user.get('first_name', 'there')},\n\n"
        f"Here is your HireMate summary:\n"
        f"- New leads in the last 24 hours: {counts['total'] or 0}\n"
        f"- Hot leads: {counts['hot'] or 0}\n"
        f"- Saved leads: {counts['saved'] or 0}\n"
        f"- Pending drafts: {drafts['pending'] or 0}\n\n"
        "Open HireMate to continue.\n\nHireMate"
    )
    html_body = email_shell(
        "Daily summary",
        (
            f"<p>New leads in the last 24 hours: <strong>{counts['total'] or 0}</strong></p>"
            f"<p>Hot leads: <strong>{counts['hot'] or 0}</strong></p>"
            f"<p>Saved leads: <strong>{counts['saved'] or 0}</strong></p>"
            f"<p>Pending drafts: <strong>{drafts['pending'] or 0}</strong></p>"
        ),
    )
    result = deliver(user, "daily_summary", subject, text, html_body)
    with db() as conn:
        conn.execute(
            "UPDATE notification_preferences SET last_daily_summary_at=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (datetime.now(PK_TZ).isoformat(), user["id"]),
        )
    return result


def email_shell(title, body_html):
    return f"""
    <div style="font-family:Arial,sans-serif;line-height:1.6;color:#111827;padding:20px">
      <div style="max-width:560px;margin:auto;border:1px solid #e5e7eb;border-radius:14px;padding:24px">
        <h2 style="margin:0 0 12px;color:#0f172a">{html.escape(title)}</h2>
        <div>{body_html}</div>
        <p style="margin-top:24px;color:#64748b;font-size:13px">This email was sent because your HireMate notification preferences allow it.</p>
      </div>
    </div>
    """
