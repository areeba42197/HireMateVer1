"""SMTP email delivery for HireMate notifications.

The frontend stores notification preferences, while this service handles the
actual email transport. Credentials stay in the backend only. Developers can
configure SMTP through environment variables or through the private
backend/secure/smtp_config.json file, which is easier during local FYP demos.
"""

from email.message import EmailMessage
import json
import os
import smtplib

from core.config import (
    SECURE_DIR,
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PASSWORD_FILE,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_USE_TLS,
)

SMTP_CONFIG_FILE = SECURE_DIR / "smtp_config.json"


def smtp_file_config():
    """Load optional local SMTP config without exposing credentials to frontend."""
    try:
        return json.loads(SMTP_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def smtp_password(file_config=None):
    """Read the SMTP password from env, JSON config, then secure password file."""
    file_config = file_config or smtp_file_config()
    if SMTP_PASSWORD:
        return SMTP_PASSWORD
    if file_config.get("password"):
        return str(file_config.get("password")).strip()
    try:
        return SMTP_PASSWORD_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def smtp_settings():
    """Return the active SMTP settings with environment variables taking priority."""
    file_config = smtp_file_config()
    host = SMTP_HOST or str(file_config.get("host", "")).strip()
    username = SMTP_USERNAME or str(file_config.get("username", "")).strip()
    from_email = SMTP_FROM_EMAIL or str(file_config.get("from_email", "")).strip() or username
    from_name = SMTP_FROM_NAME or str(file_config.get("from_name", "HireMate")).strip() or "HireMate"
    port = int(os.getenv("SMTP_PORT") or file_config.get("port", SMTP_PORT) or 587)
    if os.getenv("SMTP_USE_TLS") is not None:
        use_tls = SMTP_USE_TLS
    else:
        use_tls = str(file_config.get("use_tls", "true")).strip().lower() not in {"0", "false", "no"}

    return {
        "host": host,
        "port": int(port),
        "username": username,
        "password": smtp_password(file_config),
        "from_email": from_email,
        "from_name": from_name,
        "use_tls": use_tls,
        "config_file": str(SMTP_CONFIG_FILE),
    }


def email_status():
    """Expose safe delivery status for the settings screen."""
    settings = smtp_settings()
    configured = bool(
        settings["host"]
        and settings["port"]
        and settings["from_email"]
        and settings["username"]
        and settings["password"]
    )
    return {
        "configured": configured,
        "host": settings["host"],
        "from_email": settings["from_email"],
        "config_file": settings["config_file"],
    }


def email_is_configured():
    return email_status()["configured"]


def send_email(to_email, subject, text_body, html_body=None):
    """Send one email to the supplied user account email address."""
    settings = smtp_settings()
    if not to_email:
        raise RuntimeError("This account does not have an email address saved.")
    if not email_is_configured():
        raise RuntimeError(
            "Email delivery is not configured yet. Add SMTP settings in backend/secure/smtp_config.json, "
            "or set SMTP_HOST, SMTP_USERNAME, SMTP_FROM_EMAIL, and an SMTP password."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings['from_name']} <{settings['from_email']}>"
    message["To"] = to_email
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings["host"], settings["port"], timeout=30) as smtp:
        if settings["use_tls"]:
            smtp.starttls()
        smtp.login(settings["username"], settings["password"])
        smtp.send_message(message)

    return {"sent": True, "to": to_email, "subject": subject}

