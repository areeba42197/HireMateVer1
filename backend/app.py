import json
import mimetypes
import os
import random
import re
import threading
import time
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urlerror, request
from urllib.parse import parse_qs, unquote, urlparse

from core.config import (
    ALLOWED_STATIC_EXTENSIONS,
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    ADMIN_PIN,
    APP_HOST,
    APP_PORT,
    LINKEDIN_AUTO_SYNC_ENABLED,
    LINKEDIN_AUTO_SYNC_INTERVAL_SECONDS,
    LINKEDIN_AUTO_SYNC_JITTER_SECONDS,
    LINKEDIN_AUTO_POST_SYNC_EVERY,
    LINKEDIN_AUTO_SYNC_STARTUP_DELAY_SECONDS,
    PROJECT_DIR,
)
from core.database import db, init_db
from core.security import hash_password, iso_after, new_token, protect_text, reveal_text, token_signature_ok, verify_password
from services.ai_keyword_service import keyword_profile_for_user
from services.ai_match_service import profile_match_for_lead
from services.draft_service import delete_draft, generate_draft, get_draft, list_drafts, update_draft_status
from services.lead_service import clear_lead_cache, dashboard, get_lead, import_posts, list_leads, sample_posts, update_lead_status
from services.linkedin_browser_post_service import (
    collect_posts_with_browser,
)
from services.linkedin_post_service import collect_posts_for_profile
from services.linkedin_service import parse_manual_posts, sync_linkedin_for_profile
from services.email_service import email_is_configured, email_status
from services.notification_service import (
    maybe_send_daily_summary,
    notify_draft_approved,
    notify_hot_leads,
    send_test_email,
)
from services.public_post_search_service import collect_public_linkedin_posts


LINKEDIN_JOB_PAGE_STEP = 10
LINKEDIN_MAX_PAGES_PER_CLICK = 2
AUTH_CACHE_TTL_SECONDS = 300
_auth_user_cache = {}


def auth_cache_get(token):
    cached = _auth_user_cache.get(token)
    if not cached:
        return None
    created_at, user = cached
    if time.monotonic() - created_at > AUTH_CACHE_TTL_SECONDS:
        _auth_user_cache.pop(token, None)
        return None
    return deepcopy(user)


def auth_cache_set(token, user):
    _auth_user_cache[token] = (time.monotonic(), deepcopy(user))
    if len(_auth_user_cache) > 200:
        oldest = min(_auth_user_cache, key=lambda item: _auth_user_cache[item][0])
        _auth_user_cache.pop(oldest, None)


def auth_cache_clear(token=None, user_id=None):
    if token:
        _auth_user_cache.pop(token, None)
    if user_id is not None:
        for key, (_, user) in list(_auth_user_cache.items()):
            if str(user.get("id")) == str(user_id):
                _auth_user_cache.pop(key, None)


def json_response(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def error(handler, status, message):
    json_response(handler, status, {"ok": False, "error": message})


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length == 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw or "{}")


def post_worker_url():
    return os.getenv("POST_WORKER_URL", "").strip().rstrip("/")


def proxy_post_worker(handler, path, body):
    worker = post_worker_url()
    if not worker:
        return False
    token = handler.headers.get("Authorization", "")
    payload = json.dumps(body or {}).encode("utf-8")
    req = request.Request(
        worker + path,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": token,
        },
    )
    try:
        with request.urlopen(req, timeout=58) as response:
            raw = response.read()
            status = response.getcode()
    except urlerror.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except Exception as exc:
        return error(handler, 502, f"Collect Posts worker is not reachable yet: {exc}")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)
    return True


def normalize_linkedin_cookie(cookie):
    meta = parse_linkedin_session_input(cookie)
    cookie = meta["cookie"]
    if "li_at=" in cookie:
        return cookie
    if "=" not in cookie and len(cookie) >= 20:
        return "li_at=" + cookie
    return cookie


def parse_linkedin_session_input(value):
    value = (value or "").strip()
    meta = {"cookie": value, "user_agent": "", "accept_language": ""}
    if not value:
        return meta
    curl_cookie = extract_cookie_from_curl(value)
    if curl_cookie:
        meta["cookie"] = curl_cookie
    ua = first_regex(value, [r"-H\s+'user-agent:\s*([^']+)'", r'-H\s+"user-agent:\s*([^"]+)"'])
    if ua:
        meta["user_agent"] = ua.strip()
    lang = first_regex(value, [r"-H\s+'accept-language:\s*([^']+)'", r'-H\s+"accept-language:\s*([^"]+)"'])
    if lang:
        meta["accept_language"] = lang.strip()
    return meta


def first_regex(value, patterns):
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.I | re.S)
        if match:
            return match.group(1)
    return ""


def extract_cookie_from_curl(value):
    # Accept a full "Copy as cURL" command and keep only the Cookie header.
    patterns = [
        r"(?:^|\s)-b\s+'([^']*li_at=[^']*)'",
        r'(?:^|\s)-b\s+"([^"]*li_at=[^"]*)"',
        r"(?:^|\s)--cookie\s+'([^']*li_at=[^']*)'",
        r'(?:^|\s)--cookie\s+"([^"]*li_at=[^"]*)"',
        r"-H\s+'cookie:\s*([^']*li_at=[^']*)'",
        r'-H\s+"cookie:\s*([^"]*li_at=[^"]*)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.I | re.S)
        if match:
            return match.group(1).replace("\\\n", "").strip()
    return ""


def current_user(handler):
    auth = handler.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.replace("Bearer ", "", 1).strip()
    if not token_signature_ok(token):
        return None
    cached = auth_cache_get(token)
    if cached:
        return cached
    with db() as conn:
        row = conn.execute(
            """
            SELECT u.* FROM sessions s
            JOIN users u ON u.id=s.user_id
            WHERE s.token=? AND datetime(s.expires_at) > datetime('now')
            """,
            (token,),
        ).fetchone()
        user = dict(row) if row else None
        if user:
            auth_cache_set(token, user)
        return user


def require_user(handler):
    user = current_user(handler)
    if not user:
        error(handler, 401, "Authentication required. Please login again.")
        return None
    return user


def require_admin(handler):
    """Validate a signed admin session for the admin portal."""
    user = current_user(handler)
    if user and str(user.get("role", "user")).lower() == "admin":
        return True
    if os.getenv("ALLOW_LEGACY_ADMIN_HEADER", "").strip().lower() in {"1", "true", "yes"}:
        if handler.headers.get("X-HireMate-Admin") == "ok":
            return True
    error(handler, 401, "Administrator access required.")
    return False


class HireMateHandler(BaseHTTPRequestHandler):
    server_version = "HireMateBackend/1.0"

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.end_headers()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path == "/api/health":
                return json_response(self, 200, {"ok": True, "service": "HireMate API", "version": "vercel-cookie-fix"})
            if path == "/api/me":
                user = require_user(self)
                if user:
                    return json_response(self, 200, {"ok": True, "user": public_user(user)})
                return
            if path == "/api/dashboard":
                user = require_user(self)
                if user:
                    if not profile_complete(user):
                        return json_response(self, 200, {"ok": True, "profile_required": True, "data": empty_dashboard_data()})
                    return json_response(self, 200, {"ok": True, "data": dashboard(user["id"])})
                return
            if path == "/api/admin/summary":
                if require_admin(self):
                    return json_response(self, 200, {"ok": True, "summary": admin_summary()})
                return
            if path == "/api/admin/users":
                if require_admin(self):
                    return json_response(
                        self,
                        200,
                        {
                            "ok": True,
                            "users": admin_users(
                                search=query.get("search", [""])[0],
                                status=query.get("status", ["all"])[0],
                            ),
                        },
                    )
                return
            if path == "/api/admin/logs":
                if require_admin(self):
                    return json_response(self, 200, {"ok": True, "logs": admin_logs()})
                return
            if path == "/api/leads":
                user = require_user(self)
                if user:
                    if not profile_complete(user):
                        return json_response(self, 200, {"ok": True, "profile_required": True, **empty_leads_result()})
                    result = list_leads(
                        user["id"],
                        temperature=query.get("temperature", ["all"])[0],
                        search=query.get("search", [""])[0],
                        limit=query.get("limit", [50])[0],
                        offset=query.get("offset", [0])[0],
                        status=query.get("status", [""])[0],
                        kind=query.get("kind", ["all"])[0],
                    )
                    return json_response(self, 200, {"ok": True, "leads": result["items"], **result})
                return
            if path.startswith("/api/leads/"):
                user = require_user(self)
                if user:
                    if path.endswith("/match"):
                        lead_id = int(path.split("/")[-2])
                        lead = get_lead(user["id"], lead_id)
                        if not lead:
                            return error(self, 404, "Lead not found.")
                        if lead.get("lead_kind") == "job" and job_description_missing(lead):
                            return json_response(self, 200, {"ok": True, "match": unavailable_job_match(lead)})
                        force_match = query.get("fresh", [""])[0] in {"1", "true", "yes"}
                        match = profile_match_for_lead(dict(user), lead, force_refresh=force_match)
                        return json_response(self, 200, {"ok": True, "match": match})
                    lead_id = int(path.rsplit("/", 1)[1])
                    lead = get_lead(user["id"], lead_id)
                    if not lead:
                        return error(self, 404, "Lead not found.")
                    return json_response(self, 200, {"ok": True, "lead": lead})
                return
            if path == "/api/drafts":
                user = require_user(self)
                if user:
                    return json_response(self, 200, {"ok": True, "drafts": list_drafts(user["id"])})
                return
            if path.startswith("/api/drafts/"):
                user = require_user(self)
                if user:
                    draft_id = int(path.rsplit("/", 1)[1])
                    draft = get_draft(user["id"], draft_id)
                    if not draft:
                        return error(self, 404, "Draft not found.")
                    return json_response(self, 200, {"ok": True, "draft": draft})
                return
            if path == "/api/linkedin/cookie":
                user = require_user(self)
                if user:
                    return json_response(self, 200, {"ok": True, "cookie": cookie_status(user)})
                return
            if path == "/api/linkedin/sync-status":
                user = require_user(self)
                if user:
                    return json_response(self, 200, {"ok": True, "status": sync_status(user["id"])})
                return
            if path == "/api/settings/notifications":
                user = require_user(self)
                if user:
                    return json_response(
                        self,
                        200,
                        {
                            "ok": True,
                            "preferences": notification_preferences(user["id"]),
                            "recipient_email": user["email"],
                            "email_configured": email_is_configured(),
                            "email_status": email_status(),
                        },
                    )
                return
            if path == "/api/analytics":
                user = require_user(self)
                if user:
                    return json_response(self, 200, {"ok": True, "data": analytics(user["id"])})
                return
            if path == "/api/ai/keywords":
                user = require_user(self)
                if user:
                    return json_response(self, 200, {"ok": True, "keywords": keyword_profile_for_user(dict(user))})
                return
            return self.serve_static(path)
        except Exception as exc:
            return error(self, 500, str(exc))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            body = read_json(self)
            if path == "/api/auth/register":
                return self.register(body)
            if path == "/api/auth/login":
                return self.login(body)
            if path == "/api/auth/forgot-password":
                return self.forgot_password(body)
            if path == "/api/auth/reset-password":
                return self.reset_password(body)
            if path == "/api/admin/login":
                return self.admin_login(body)
            if path == "/api/auth/logout":
                user = current_user(self)
                token = self.headers.get("Authorization", "").replace("Bearer ", "", 1)
                with db() as conn:
                    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
                    if user:
                        conn.execute("INSERT INTO events(user_id, event_type) VALUES (?, ?)", (user["id"], "logout"))
                auth_cache_clear(token=token)
                return json_response(self, 200, {"ok": True})
            if path.startswith("/api/admin/users/") and path.endswith("/reset-password"):
                if require_admin(self):
                    user_id = int(path.split("/")[-2])
                    result = admin_reset_password(user_id, body.get("password", ""))
                    if not result:
                        return error(self, 404, "User account not found.")
                    return json_response(self, 200, {"ok": True, "user": result})
                return
            if path == "/api/linkedin/import-sample":
                user = require_user(self)
                if user:
                    if not profile_complete(user):
                        return error(self, 400, "Complete your profile first so HireMate can find leads that match you.")
                    imported = import_posts(user["id"], sample_posts())
                    return json_response(self, 200, {"ok": True, "imported": len(imported)})
                return
            if path == "/api/linkedin/import-posts":
                user = require_user(self)
                if user:
                    if not profile_complete(user):
                        return error(self, 400, "Complete your profile first so HireMate can find leads that match you.")
                    posts = parse_manual_posts(body.get("posts", []))
                    imported = import_posts(user["id"], posts)
                    return json_response(self, 200, {"ok": True, "imported": len(imported), "leads": imported})
                return
            if path == "/api/linkedin/collect-visible":
                user = require_user(self)
                if user:
                    if not profile_complete(user):
                        return error(self, 400, "Complete your profile first so HireMate can find leads that match you.")
                    posts = parse_manual_posts(body.get("posts", []))
                    if not posts:
                        return error(self, 400, "No visible LinkedIn posts were received.")
                    imported = import_posts(user["id"], posts)
                    previous = sync_status(user["id"])
                    previous_jobs = int(previous.get("job_count") or 0)
                    record_sync_event(user["id"], len(imported), len(imported), previous_jobs, [], checked_post_count=len(posts), checked_job_count=0)
                    return json_response(self, 200, {"ok": True, "imported": len(imported), "post_count": len(imported), "job_count": previous_jobs, "checked_post_count": len(posts), "checked_job_count": 0, "leads": imported})
                return
            if path == "/api/linkedin/sync-posts":
                user = require_user(self)
                if user:
                    if not profile_complete(user):
                        return error(self, 400, "Complete your profile first so HireMate can find leads that match you.")
                    sync_user = dict(user)
                    cipher = sync_user.get("linkedin_cookie_cipher") or ""
                    sync_user["linkedin_cookie"] = reveal_text(cipher) if cipher else ""
                    cursor = linkedin_cursor(user["id"])
                    posts, errors, post_meta = collect_posts_for_profile(
                        sync_user,
                        keyword_offset=int(cursor.get("content_start") or 0),
                        result_start=int(cursor.get("job_start") or 0),
                        include_meta=True,
                    )
                    source = "linkedin-session"
                    if not posts:
                        public_posts, public_errors, public_meta = collect_public_linkedin_posts(
                            sync_user,
                            keyword_offset=int(cursor.get("content_start") or 0),
                            include_meta=True,
                        )
                        posts = public_posts
                        errors.extend(public_errors)
                        post_meta = public_meta
                        source = "public-index"
                    imported = import_posts(user["id"], posts) if posts else []
                    keywords_used = post_meta.get("keywords_used", [])
                    keyword_count = int(post_meta.get("keyword_count") or 0)
                    next_keyword_offset = int(cursor.get("content_start") or 0) + max(1, len(keywords_used))
                    next_result_start = int(cursor.get("job_start") or 0) + LINKEDIN_JOB_PAGE_STEP
                    save_linkedin_cursor(user["id"], next_result_start, next_keyword_offset)
                    if imported or posts:
                        record_sync_event(
                            user["id"],
                            len(imported),
                            len(imported),
                            0,
                            errors,
                            checked_post_count=len(posts),
                            checked_job_count=0,
                        )
                    if imported:
                        try:
                            notify_hot_leads(dict(user), imported)
                        except Exception:
                            pass
                    return json_response(
                        self,
                        200,
                        {
                            "ok": True,
                            "imported": len(imported),
                            "post_count": len(imported),
                            "job_count": 0,
                            "checked_post_count": len(posts),
                            "checked_job_count": 0,
                            "next_keyword_offset": next_keyword_offset,
                            "next_result_start": next_result_start,
                            "source": source,
                            "keywords_used": keywords_used,
                            "keyword_count": keyword_count,
                            "leads": imported,
                            "errors": errors[:5],
                        },
                    )
                return
            if path == "/api/linkedin/sync-posts-browser":
                if proxy_post_worker(self, path, body):
                    return
                user = require_user(self)
                if user:
                    if not profile_complete(user):
                        return error(self, 400, "Complete your profile first so HireMate can find leads that match you.")
                    sync_user = dict(user)
                    cipher = sync_user.get("linkedin_cookie_cipher") or ""
                    sync_user["linkedin_cookie"] = reveal_text(cipher) if cipher else ""
                    cursor = linkedin_cursor(user["id"])
                    posts, errors = collect_posts_with_browser(
                        sync_user,
                        keyword_offset=int(cursor.get("content_start") or 0),
                        max_posts=4,
                        scrolls=1,
                        exact_link_limit=0,
                    )
                    imported = import_posts(user["id"], posts) if posts else []
                    next_keyword_offset = int(cursor.get("content_start") or 0) + 1
                    save_linkedin_cursor(user["id"], int(cursor.get("job_start") or 0), next_keyword_offset)
                    previous = sync_status(user["id"])
                    previous_jobs = int(previous.get("job_count") or 0)
                    record_sync_event(
                        user["id"],
                        len(imported),
                        len(imported),
                        previous_jobs,
                        errors,
                        checked_post_count=len(posts),
                        checked_job_count=0,
                    )
                    return json_response(
                        self,
                        200,
                        {
                            "ok": True,
                            "imported": len(imported),
                            "post_count": len(imported),
                            "job_count": 0,
                            "checked_post_count": len(posts),
                            "checked_job_count": 0,
                            "next_keyword_offset": next_keyword_offset,
                            "source": "selenium-browser",
                            "leads": imported,
                            "errors": errors[:5],
                        },
                    )
                return
            if path == "/api/linkedin/sync":
                user = require_user(self)
                if user:
                    if not profile_complete(user):
                        return error(self, 400, "Complete your profile first so HireMate can find leads that match you.")
                    sync_user = dict(user)
                    cipher = sync_user.get("linkedin_cookie_cipher") or ""
                    sync_user["linkedin_cookie"] = reveal_text(cipher) if cipher else ""
                    cursor = linkedin_cursor(user["id"])
                    posts, errors, imported, pages_scanned, next_start, next_keyword_offset = sync_until_new_leads(
                        sync_user,
                        user["id"],
                        int(cursor.get("job_start") or 0),
                        int(cursor.get("content_start") or 0),
                    )
                    if not posts:
                        # A stale/expired LinkedIn session can prevent post search, but public
                        # LinkedIn Jobs should still be tried from the first page for this user.
                        jobs_user = dict(sync_user)
                        jobs_user["linkedin_cookie"] = ""
                        posts, retry_errors, imported, retry_pages, next_start, next_keyword_offset = sync_until_new_leads(
                            jobs_user,
                            user["id"],
                            0,
                            int(cursor.get("content_start") or 0) + 2,
                        )
                        errors.extend(retry_errors)
                        pages_scanned += retry_pages
                    if not posts:
                        record_sync_event(user["id"], 0, 0, 0, errors, checked_post_count=0, checked_job_count=0)
                        return json_response(
                            self,
                            200,
                            {
                                "ok": True,
                                "imported": 0,
                                "post_count": 0,
                                "job_count": 0,
                                "checked_post_count": 0,
                                "checked_job_count": 0,
                                "pages_scanned": pages_scanned,
                                "next_job_start": next_start,
                                "next_keyword_offset": next_keyword_offset,
                                "leads": [],
                                "errors": errors[:5],
                            },
                        )
                    save_linkedin_cursor(user["id"], next_start, next_keyword_offset)
                    post_count = len([p for p in imported if p.get("lead_kind") == "post"])
                    job_count = len([p for p in imported if p.get("lead_kind") == "job"])
                    checked_post_count = len([p for p in posts if p.get("lead_kind") == "post"])
                    checked_job_count = len([p for p in posts if p.get("lead_kind") == "job"])
                    record_sync_event(user["id"], len(imported), post_count, job_count, errors, checked_post_count=checked_post_count, checked_job_count=checked_job_count)
                    if imported:
                        try:
                            notify_hot_leads(dict(user), imported)
                        except Exception:
                            pass
                    return json_response(self, 200, {"ok": True, "imported": len(imported), "post_count": post_count, "job_count": job_count, "checked_post_count": checked_post_count, "checked_job_count": checked_job_count, "pages_scanned": pages_scanned, "next_job_start": next_start, "next_keyword_offset": next_keyword_offset, "leads": imported, "errors": errors[:5]})
                return
            if path == "/api/linkedin/cookie":
                user = require_user(self)
                if user:
                    return self.update_linkedin_cookie(user, body)
                return
            if path == "/api/ai/keywords":
                user = require_user(self)
                if user:
                    return json_response(self, 200, {"ok": True, "keywords": keyword_profile_for_user(dict(user), force_refresh=True)})
                return
            if path == "/api/settings/notifications/test":
                user = require_user(self)
                if user:
                    try:
                        send_test_email(dict(user))
                        message = f"Test notification sent to {user['email']}."
                        return json_response(self, 200, {"ok": True, "sent": True, "recipient_email": user["email"], "message": message})
                    except Exception:
                        message = f"Notifications are active for {user['email']}."
                        return json_response(self, 200, {"ok": True, "sent": False, "queued": True, "recipient_email": user["email"], "message": message})
                return
            if path == "/api/drafts/generate":
                user = require_user(self)
                if user:
                    lead = get_lead(user["id"], int(body.get("lead_id")))
                    if not lead:
                        return error(self, 404, "Lead not found.")
                    draft = generate_draft(user["id"], lead, body.get("draft_type", "message"), body.get("tone", "professional"))
                    return json_response(self, 200, {"ok": True, "draft": draft})
                return
            return error(self, 404, "API endpoint not found.")
        except Exception as exc:
            return error(self, 500, str(exc))

    def do_PATCH(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/profile":
                user = require_user(self)
                if user:
                    body = read_json(self)
                    return self.update_profile(user, body)
                return
            if path == "/api/account/password":
                user = require_user(self)
                if user:
                    body = read_json(self)
                    return self.update_password(user, body)
                return
            if path == "/api/settings/notifications":
                user = require_user(self)
                if user:
                    body = read_json(self)
                    prefs = save_notification_preferences(user["id"], body)
                    return json_response(self, 200, {"ok": True, "preferences": prefs, "recipient_email": user["email"], "email_configured": email_is_configured(), "email_status": email_status()})
                return
            if path.startswith("/api/leads/"):
                user = require_user(self)
                if user:
                    lead_id = int(path.rsplit("/", 1)[1])
                    body = read_json(self)
                    lead = update_lead_status(user["id"], lead_id, body.get("status", "new"))
                    if not lead:
                        return error(self, 404, "Lead not found.")
                    return json_response(self, 200, {"ok": True, "lead": lead})
                return
            if path.startswith("/api/drafts/"):
                user = require_user(self)
                if user:
                    draft_id = int(path.rsplit("/", 1)[1])
                    body = read_json(self)
                    draft = update_draft_status(user["id"], draft_id, body.get("status", "pending"), body.get("content"))
                    if not draft:
                        return error(self, 404, "Draft not found.")
                    if body.get("status") == "approved":
                        try:
                            notify_draft_approved(user["id"], draft)
                        except Exception as exc:
                            draft["email_warning"] = str(exc)
                    return json_response(self, 200, {"ok": True, "draft": draft})
                return
            if path.startswith("/api/admin/users/"):
                if require_admin(self):
                    user_id = int(path.rsplit("/", 1)[1])
                    body = read_json(self)
                    result = admin_update_user(user_id, body)
                    if not result:
                        return error(self, 404, "User account not found.")
                    return json_response(self, 200, {"ok": True, "user": result})
                return
            return error(self, 404, "API endpoint not found.")
        except Exception as exc:
            return error(self, 500, str(exc))

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/linkedin/cookie":
                user = require_user(self)
                if user:
                    return self.disconnect_linkedin_cookie(user)
                return
            if path == "/api/account":
                user = require_user(self)
                if user:
                    token = self.headers.get("Authorization", "").replace("Bearer ", "", 1)
                    delete_account(user["id"])
                    auth_cache_clear(token=token, user_id=user["id"])
                    return json_response(self, 200, {"ok": True})
                return
            if path.startswith("/api/drafts/"):
                user = require_user(self)
                if user:
                    draft_id = int(path.rsplit("/", 1)[1])
                    if not delete_draft(user["id"], draft_id):
                        return error(self, 404, "Draft not found.")
                    return json_response(self, 200, {"ok": True})
                return
            return error(self, 404, "API endpoint not found.")
        except Exception as exc:
            return error(self, 500, str(exc))

    def register(self, body):
        required = ["first_name", "last_name", "email", "password"]
        if any(not str(body.get(field, "")).strip() for field in required):
            return error(self, 400, "First name, last name, email and password are required.")
        session_meta = parse_linkedin_session_input(body.get("linkedin_cookie", ""))
        cookie = normalize_linkedin_cookie(body.get("linkedin_cookie", ""))
        if cookie and "li_at=" not in cookie:
            return error(self, 400, "LinkedIn cookie must include li_at= or be the raw li_at value.")
        with db() as conn:
            existing = conn.execute("SELECT id FROM users WHERE lower(email)=lower(?)", (body["email"],)).fetchone()
            if existing:
                return error(self, 409, "An account with this email already exists.")
            cur = conn.execute(
                """
                INSERT INTO users(first_name, last_name, email, password_hash, linkedin_cookie_cipher, linkedin_user_agent, linkedin_accept_language, skills, interests)
                VALUES (?, ?, ?, ?, ?, ?, ?, '', '')
                """,
                (
                    body["first_name"].strip(),
                    body["last_name"].strip(),
                    body["email"].strip().lower(),
                    hash_password(body["password"]),
                    protect_text(cookie) if cookie else "",
                    session_meta["user_agent"],
                    session_meta["accept_language"],
                ),
            )
            user_id = cur.lastrowid
            conn.execute("INSERT INTO events(user_id, event_type) VALUES (?, ?)", (user_id, "register"))
        return create_session_response(self, user_id)

    def update_profile(self, user, body):
        fields = {
            "first_name": body.get("first_name", user["first_name"]),
            "last_name": body.get("last_name", user["last_name"]),
            "headline": body.get("headline", user.get("headline", "")),
            "location": body.get("location", user.get("location", "")),
            "about": body.get("about", user.get("about", "")),
            "skills": body.get("skills", user.get("skills", "")),
            "interests": body.get("interests", user.get("interests", "")),
            "target_roles": body.get("target_roles", user.get("target_roles", "")),
            "preferred_locations": body.get("preferred_locations", user.get("preferred_locations", "")),
            "work_modes": body.get("work_modes", user.get("work_modes", "")),
            "experience_level": body.get("experience_level", user.get("experience_level", "")),
            "education": body.get("education", user.get("education", "")),
            "experience_detail": body.get("experience_detail", user.get("experience_detail", "")),
            "avatar_image": body.get("avatar_image", user.get("avatar_image", "")),
            "cover_image": body.get("cover_image", user.get("cover_image", "")),
        }
        profile_search_fields = (
            "headline", "location", "about", "skills", "interests", "target_roles",
            "preferred_locations", "work_modes", "experience_level", "education", "experience_detail"
        )
        profile_changed = any(
            str(fields[key] or "").strip() != str(user.get(key, "") or "").strip()
            for key in profile_search_fields
        )
        for image_key in ("avatar_image", "cover_image"):
            image_value = fields[image_key] or ""
            if image_value and (not image_value.startswith("data:image/") or len(image_value) > 1500000):
                return error(self, 400, "Profile images must be PNG/JPEG/WebP data under 1.5 MB.")
        session_meta = parse_linkedin_session_input(body.get("linkedin_cookie"))
        cookie = normalize_linkedin_cookie(body.get("linkedin_cookie"))
        with db() as conn:
            conn.execute(
                """
                UPDATE users SET
                  first_name=?, last_name=?, headline=?, location=?, about=?, skills=?, interests=?,
                  target_roles=?, preferred_locations=?, work_modes=?, experience_level=?, education=?, experience_detail=?,
                  avatar_image=?, cover_image=?
                WHERE id=?
                """,
                (
                    fields["first_name"],
                    fields["last_name"],
                    fields["headline"],
                    fields["location"],
                    fields["about"],
                    fields["skills"],
                    fields["interests"],
                    fields["target_roles"],
                    fields["preferred_locations"],
                    fields["work_modes"],
                    fields["experience_level"],
                    fields["education"],
                    fields["experience_detail"],
                    fields["avatar_image"],
                    fields["cover_image"],
                    user["id"],
                ),
            )
            if cookie:
                if "li_at=" not in cookie:
                    return error(self, 400, "LinkedIn cookie must include li_at= or be the raw li_at value.")
                conn.execute(
                    "UPDATE users SET linkedin_cookie_cipher=?, linkedin_user_agent=COALESCE(NULLIF(?, ''), linkedin_user_agent), linkedin_accept_language=COALESCE(NULLIF(?, ''), linkedin_accept_language) WHERE id=?",
                    (protect_text(cookie), session_meta["user_agent"], session_meta["accept_language"], user["id"]),
                )
            if profile_changed:
                conn.execute("DELETE FROM ai_keyword_profiles WHERE user_id=?", (user["id"],))
                conn.execute(
                    """
                    INSERT INTO linkedin_cursors(user_id, job_start, content_start, updated_at)
                    VALUES (?, 0, 0, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                      job_start=0,
                      content_start=0,
                      updated_at=CURRENT_TIMESTAMP
                    """,
                    (user["id"],),
                )
            conn.execute("INSERT INTO events(user_id, event_type) VALUES (?, ?)", (user["id"], "profile_onboarding_saved"))
            updated = dict(conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())
        auth_cache_clear(user_id=user["id"])
        if profile_changed:
            clear_lead_cache(user["id"])
        return json_response(self, 200, {"ok": True, "user": public_user(updated)})

    def update_linkedin_cookie(self, user, body):
        session_meta = parse_linkedin_session_input(body.get("linkedin_cookie"))
        cookie = normalize_linkedin_cookie(body.get("linkedin_cookie"))
        if not cookie:
            return error(self, 400, "LinkedIn cookie is required.")
        if "li_at=" not in cookie:
            return error(self, 400, "LinkedIn cookie must include li_at= or be the raw li_at value.")
        with db() as conn:
            conn.execute(
                "UPDATE users SET linkedin_cookie_cipher=?, linkedin_user_agent=COALESCE(NULLIF(?, ''), linkedin_user_agent), linkedin_accept_language=COALESCE(NULLIF(?, ''), linkedin_accept_language) WHERE id=?",
                (protect_text(cookie), session_meta["user_agent"], session_meta["accept_language"], user["id"]),
            )
            conn.execute("INSERT INTO events(user_id, event_type) VALUES (?, ?)", (user["id"], "linkedin_cookie_updated"))
            updated = dict(conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())
        auth_cache_clear(user_id=user["id"])
        return json_response(self, 200, {"ok": True, "user": public_user(updated), "cookie_connected": True})

    def disconnect_linkedin_cookie(self, user):
        with db() as conn:
            conn.execute(
                """
                UPDATE users
                SET linkedin_cookie_cipher='', linkedin_user_agent='', linkedin_accept_language=''
                WHERE id=?
                """,
                (user["id"],),
            )
            conn.execute("DELETE FROM linkedin_cursors WHERE user_id=?", (user["id"],))
            conn.execute("INSERT INTO events(user_id, event_type) VALUES (?, ?)", (user["id"], "linkedin_cookie_disconnected"))
            updated = dict(conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())
        auth_cache_clear(user_id=user["id"])
        return json_response(
            self,
            200,
            {
                "ok": True,
                "user": public_user(updated),
                "cookie": {"connected": False, "masked": "", "updated_hint": ""},
                "cookie_connected": False,
            },
        )

    def update_password(self, user, body):
        current_password = str(body.get("current_password", ""))
        new_password = str(body.get("new_password", ""))
        if not current_password:
            return error(self, 400, "Current password is required.")
        if not verify_password(current_password, user["password_hash"]):
            return error(self, 403, "Current password is incorrect.")
        if len(new_password) < 8:
            return error(self, 400, "New password must be at least 8 characters.")
        if not re.search(r"[A-Z]", new_password):
            return error(self, 400, "New password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", new_password):
            return error(self, 400, "New password must contain at least one lowercase letter.")
        if not re.search(r"[0-9]", new_password):
            return error(self, 400, "New password must contain at least one number.")
        if not re.search(r"[^A-Za-z0-9]", new_password):
            return error(self, 400, "New password must contain at least one special character.")
        with db() as conn:
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new_password), user["id"]))
            conn.execute("INSERT INTO events(user_id, event_type, details) VALUES (?, ?, ?)", (user["id"], "password_changed", "user_settings"))
        return json_response(self, 200, {"ok": True})

    def login(self, body):
        with db() as conn:
            row = conn.execute("SELECT * FROM users WHERE lower(email)=lower(?) AND is_active=1", (body.get("email", ""),)).fetchone()
            if not row or not verify_password(body.get("password", ""), row["password_hash"]):
                return error(self, 401, "Invalid email or password.")
            conn.execute("INSERT INTO events(user_id, event_type) VALUES (?, ?)", (row["id"], "login"))
        return create_session_response(self, row["id"])

    def admin_login(self, body):
        email = str(body.get("email", "")).strip().lower()
        password = str(body.get("password", ""))
        pin = str(body.get("pin", "")).strip()
        if not email or not password or not pin:
            return error(self, 400, "Admin email, password, and security PIN are required.")
        if pin != ADMIN_PIN:
            return error(self, 401, "Admin security PIN is incorrect.")
        with db() as conn:
            row = conn.execute("SELECT * FROM users WHERE lower(email)=lower(?) AND is_active=1", (email,)).fetchone()
            if not row or str(row["role"] or "user").lower() != "admin" or not verify_password(password, row["password_hash"]):
                return error(self, 401, "Admin sign in failed. Please check your details.")
            conn.execute("INSERT INTO events(user_id, event_type) VALUES (?, ?)", (row["id"], "admin_login"))
        return create_session_response(self, row["id"])

    def forgot_password(self, body):
        email = str(body.get("email", "")).strip().lower()
        if not email:
            return error(self, 400, "Please enter your email address.")
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
            return error(self, 400, "Please enter a valid email address.")
        if not email_is_configured():
            return error(self, 503, "Password reset email is not available yet. Please try again later or contact support.")
        success_msg = (
            "We've sent a password reset link to your email. Please check your inbox and spam folder."
        )
        with db() as conn:
            row = conn.execute(
                "SELECT id, first_name, email FROM users WHERE lower(email)=lower(?) AND is_active=1",
                (email,),
            ).fetchone()
            if not row:
                return error(self, 404, "We couldn't find a HireMate account with that email address.")
            user = dict(row)
            # Invalidate any existing unused tokens for this user
            conn.execute(
                "UPDATE password_reset_tokens SET used=1 WHERE user_id=? AND used=0",
                (user["id"],),
            )
            # Generate a secure reset token (1 hour expiry)
            token = new_token()
            expires_at = iso_after(1)  # 1 hour
            conn.execute(
                "INSERT INTO password_reset_tokens(user_id, token, expires_at) VALUES (?, ?, ?)",
                (user["id"], token, expires_at),
            )
            conn.execute(
                "INSERT INTO events(user_id, event_type, details) VALUES (?, ?, ?)",
                (user["id"], "password_reset_requested", email),
            )
        # Build reset link
        reset_link = _build_reset_link(token)
        # Send email
        try:
            _send_password_reset_email(user, reset_link)
        except Exception as exc:
            print(f"[WARN] Password reset email failed for {email}: {exc}")
            with db() as conn:
                conn.execute(
                    "UPDATE password_reset_tokens SET used=1 WHERE user_id=? AND used=0",
                    (user["id"],),
                )
            return error(self, 503, "We couldn't send the reset email right now. Please try again in a few minutes.")
        return json_response(self, 200, {"ok": True, "message": success_msg})

    def reset_password(self, body):
        token = str(body.get("token", "")).strip()
        new_password = str(body.get("password", ""))
        if not token:
            return error(self, 400, "Reset token is missing. Please use the link from your email.")
        if not token_signature_ok(token):
            return error(self, 400, "This reset link is invalid. Please request a new password reset.")
        if len(new_password) < 8:
            return error(self, 400, "Password must be at least 8 characters.")
        if not re.search(r"[A-Z]", new_password):
            return error(self, 400, "Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", new_password):
            return error(self, 400, "Password must contain at least one lowercase letter.")
        if not re.search(r"[0-9]", new_password):
            return error(self, 400, "Password must contain at least one number.")
        if not re.search(r"[^A-Za-z0-9]", new_password):
            return error(self, 400, "Password must contain at least one special character.")
        with db() as conn:
            row = conn.execute(
                """
                SELECT prt.id, prt.user_id, prt.used, prt.expires_at
                FROM password_reset_tokens prt
                WHERE prt.token=?
                """,
                (token,),
            ).fetchone()
            if not row:
                return error(self, 400, "This reset link is invalid or has expired. Please request a new one.")
            token_row = dict(row)
            if token_row["used"]:
                return error(self, 400, "This reset link has already been used. Please request a new password reset.")
            # Check expiry - compare as strings (ISO format) or parse
            try:
                from datetime import datetime, timezone
                expires = datetime.fromisoformat(token_row["expires_at"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > expires:
                    return error(self, 400, "This reset link has expired. Please request a new password reset.")
            except Exception:
                pass  # If parsing fails, allow the reset
            # Verify user exists and is active
            user_row = conn.execute(
                "SELECT id, email FROM users WHERE id=? AND is_active=1",
                (token_row["user_id"],),
            ).fetchone()
            if not user_row:
                return error(self, 400, "This account is no longer active. Please contact support.")
            # Update password
            conn.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (hash_password(new_password), token_row["user_id"]),
            )
            # Mark token as used
            conn.execute(
                "UPDATE password_reset_tokens SET used=1 WHERE id=?",
                (token_row["id"],),
            )
            # Invalidate all sessions for this user (security best practice)
            conn.execute(
                "DELETE FROM sessions WHERE user_id=?",
                (token_row["user_id"],),
            )
            conn.execute(
                "INSERT INTO events(user_id, event_type, details) VALUES (?, ?, ?)",
                (token_row["user_id"], "password_reset_completed", "via_email_link"),
            )
            auth_cache_clear(user_id=token_row["user_id"])
        return json_response(self, 200, {
            "ok": True,
            "message": "Your password has been reset successfully. You can now sign in with your new password.",
        })

    def serve_static(self, path):
        if path in ("", "/"):
            path = "/landing.html"
        safe = unquote(path).lstrip("/").replace("/", "\\")
        file_path = (PROJECT_DIR / safe).resolve()
        if PROJECT_DIR not in file_path.parents and file_path != PROJECT_DIR:
            return error(self, 403, "Forbidden.")
        if file_path.suffix.lower() not in ALLOWED_STATIC_EXTENSIONS or not file_path.exists():
            return error(self, 404, "File not found.")
        ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def create_session_response(handler, user_id):
    token = new_token()
    expires_at = iso_after(24)
    with db() as conn:
        conn.execute("INSERT INTO sessions(token, user_id, expires_at) VALUES (?, ?, ?)", (token, user_id, expires_at))
        user = dict(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
    auth_cache_set(token, user)
    return json_response(handler, 200, {"ok": True, "token": token, "expires_at": expires_at, "user": public_user(user)})


def profile_complete(user):
    skills = str(user.get("skills", "") or "").strip()
    roles = str(user.get("target_roles", "") or "").strip()
    context = any(
        str(user.get(key, "") or "").strip()
        for key in ("headline", "about", "education", "experience_detail", "interests")
    )
    return bool((skills or roles) and (roles or context))


def empty_leads_result():
    counts = {"total": 0, "hot": 0, "warm": 0, "cold": 0, "saved": 0, "all_kinds_total": 0, "jobs": 0, "posts": 0}
    today = {"total": 0, "hot": 0, "warm": 0, "cold": 0, "saved": 0}
    return {"items": [], "leads": [], "total": 0, "next_offset": 0, "has_more": False, "counts": counts, "today_counts": today}


def empty_dashboard_data():
    return {
        "counts": {"total": 0, "hot": 0, "warm": 0, "cold": 0, "saved": 0},
        "today_counts": {"total": 0, "hot": 0, "warm": 0, "cold": 0, "saved": 0},
        "pending_drafts": 0,
        "approved_drafts": 0,
        "approved_week_delta": 0,
        "recent_leads": [],
        "hot_leads": [],
        "drafts": [],
        "skills": [],
    }


def public_user(user):
    cookie_plain = reveal_text(user.get("linkedin_cookie_cipher") or "") if user.get("linkedin_cookie_cipher") else ""
    skills = user.get("skills", "")
    interests = user.get("interests", "")
    old_defaults_only = (
        skills == "React, JavaScript, Python, Django, Node, CSS, HTML"
        and interests == "Remote, Internship, Frontend, AI, Freelance"
        and not str(user.get("headline", "") or "").strip()
        and not str(user.get("about", "") or "").strip()
        and not str(user.get("target_roles", "") or "").strip()
    )
    if old_defaults_only:
        skills = ""
        interests = ""
    return {
        "id": user["id"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "email": user["email"],
        "headline": user.get("headline", ""),
        "location": user.get("location", ""),
        "about": user.get("about", ""),
        "skills": skills,
        "interests": interests,
        "target_roles": user.get("target_roles", ""),
        "preferred_locations": user.get("preferred_locations", ""),
        "work_modes": user.get("work_modes", ""),
        "experience_level": user.get("experience_level", ""),
        "education": user.get("education", ""),
        "experience_detail": user.get("experience_detail", ""),
        "avatar_image": user.get("avatar_image", ""),
        "cover_image": user.get("cover_image", ""),
        "profile_complete": profile_complete(user),
        "cookie_connected": bool(cookie_plain and "li_at=" in cookie_plain),
        "role": user.get("role", "user"),
    }


def admin_summary():
    with db() as conn:
        users = conn.execute(
            """
            SELECT
              COUNT(*) total,
              SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) active,
              SUM(CASE WHEN is_active=0 THEN 1 ELSE 0 END) inactive
            FROM users
            """
        ).fetchone()
        sessions = conn.execute("SELECT COUNT(*) active FROM sessions WHERE datetime(expires_at) > datetime('now')").fetchone()
        leads = conn.execute("SELECT COUNT(*) total FROM leads").fetchone()
        logs = conn.execute("SELECT COUNT(*) total FROM events WHERE event_type LIKE 'admin_%'").fetchone()
    return {
        "total_users": users["total"] or 0,
        "active_users": users["active"] or 0,
        "inactive_users": users["inactive"] or 0,
        "active_sessions": sessions["active"] or 0,
        "total_leads": leads["total"] or 0,
        "admin_actions": logs["total"] or 0,
    }


def admin_users(search="", status="all"):
    where = []
    params = []
    if status == "active":
        where.append("u.is_active=1")
    elif status == "inactive":
        where.append("u.is_active=0")
    if search:
        where.append("(u.first_name LIKE ? OR u.last_name LIKE ? OR u.email LIKE ? OR u.headline LIKE ?)")
        q = f"%{search}%"
        params.extend([q, q, q, q])
    clause = "WHERE " + " AND ".join(where) if where else ""
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT
              u.id, u.first_name, u.last_name, u.email, u.headline, u.location,
              u.role, u.is_active, u.created_at,
              COUNT(DISTINCT l.id) lead_count,
              COUNT(DISTINCT d.id) draft_count,
              MAX(s.created_at) last_session_at
            FROM users u
            LEFT JOIN leads l ON l.user_id=u.id
            LEFT JOIN drafts d ON d.user_id=u.id
            LEFT JOIN sessions s ON s.user_id=u.id AND datetime(s.expires_at) > datetime('now')
            {clause}
            GROUP BY u.id
            ORDER BY datetime(u.created_at) DESC, u.id DESC
            LIMIT 100
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def admin_update_user(user_id, body):
    first_name = str(body.get("first_name", "")).strip()
    last_name = str(body.get("last_name", "")).strip()
    email = str(body.get("email", "")).strip().lower()
    headline = str(body.get("headline", "")).strip()
    location = str(body.get("location", "")).strip()
    is_active = 1 if str(body.get("is_active", "1")) in {"1", "true", "active", "True"} else 0
    if not first_name or not last_name or not email:
        raise ValueError("First name, last name, and email are required.")
    with db() as conn:
        row = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return None
        conn.execute(
            """
            UPDATE users
            SET first_name=?, last_name=?, email=?, headline=?, location=?, is_active=?
            WHERE id=?
            """,
            (first_name, last_name, email, headline, location, is_active, user_id),
        )
        conn.execute(
            "INSERT INTO events(user_id, event_type, details) VALUES (?, ?, ?)",
            (user_id, "admin_user_updated", json.dumps({"email": email, "is_active": is_active}, ensure_ascii=False)),
        )
    return admin_user_by_id(user_id)


def admin_reset_password(user_id, password):
    password = str(password or "")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    with db() as conn:
        row = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), user_id))
        conn.execute(
            "INSERT INTO events(user_id, event_type, details) VALUES (?, ?, ?)",
            (user_id, "admin_password_reset", json.dumps({"policy": "minimum_8_characters"}, ensure_ascii=False)),
        )
    return admin_user_by_id(user_id)


def delete_account(user_id):
    with db() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM drafts WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM ai_profile_matches WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM ai_keyword_profiles WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM notification_preferences WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM password_reset_tokens WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM leads WHERE user_id=?", (user_id,))
        conn.execute("UPDATE events SET user_id=NULL WHERE user_id=?", (user_id,))
        conn.execute("UPDATE email_notifications SET user_id=NULL WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM linkedin_cursors WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    clear_lead_cache(user_id)
    auth_cache_clear(user_id=user_id)


def admin_user_by_id(user_id):
    users = admin_users(search="", status="all")
    for user in users:
        if int(user["id"]) == int(user_id):
            return user
    return None


def admin_logs():
    with db() as conn:
        rows = conn.execute(
            """
            SELECT e.id, e.event_type, e.details, e.created_at,
                   u.first_name, u.last_name, u.email
            FROM events e
            LEFT JOIN users u ON u.id=e.user_id
            WHERE e.event_type LIKE 'admin_%' OR e.event_type IN ('register', 'login', 'logout')
            ORDER BY datetime(e.created_at) DESC, e.id DESC
            LIMIT 80
            """
        ).fetchall()
    return [dict(row) for row in rows]


def cookie_status(user):
    cipher = user.get("linkedin_cookie_cipher") or ""
    if not cipher:
        return {"connected": False, "masked": "", "updated_hint": ""}
    plain = reveal_text(cipher)
    if not plain or "li_at=" not in plain:
        return {"connected": False, "masked": "", "updated_hint": ""}
    suffix = plain[-6:] if len(plain) >= 6 else "saved"
    return {
        "connected": True,
        "masked": "li_at=" + ("*" * 18) + suffix,
        "updated_hint": "Saved encrypted",
    }
    try:
        plain = reveal_text(cipher)
    except Exception:
        return {"connected": True, "masked": "li_at=â€¢â€¢â€¢â€¢â€¢â€¢", "updated_hint": "encrypted"}
    suffix = plain[-6:] if len(plain) >= 6 else "saved"
    return {
        "connected": True,
        "masked": "li_at=" + ("â€¢" * 18) + suffix,
        "updated_hint": "Saved encrypted",
    }


def bool_to_int(value):
    return 1 if value in (True, 1, "1", "true", "True", "on", "yes") else 0


def notification_preferences(user_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM notification_preferences WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            conn.execute("INSERT INTO notification_preferences(user_id) VALUES (?)", (user_id,))
            row = conn.execute("SELECT * FROM notification_preferences WHERE user_id=?", (user_id,)).fetchone()
    return {
        "hot_lead_alerts": bool(row["hot_lead_alerts"]),
        "daily_summary": bool(row["daily_summary"]),
        "draft_confirmations": bool(row["draft_confirmations"]),
        "updated_at": row["updated_at"],
    }


def save_notification_preferences(user_id, body):
    hot = bool_to_int(body.get("hot_lead_alerts", True))
    daily = bool_to_int(body.get("daily_summary", True))
    drafts = bool_to_int(body.get("draft_confirmations", True))
    with db() as conn:
        conn.execute(
            """
            INSERT INTO notification_preferences(user_id, hot_lead_alerts, daily_summary, draft_confirmations, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
              hot_lead_alerts=excluded.hot_lead_alerts,
              daily_summary=excluded.daily_summary,
              draft_confirmations=excluded.draft_confirmations,
              updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, hot, daily, drafts),
        )
        conn.execute(
            "INSERT INTO events(user_id, event_type, details) VALUES (?, ?, ?)",
            (user_id, "notification_preferences_updated", json.dumps({"hot": hot, "daily": daily, "drafts": drafts})),
        )
    return notification_preferences(user_id)


def record_sync_event(user_id, imported, post_count, job_count, errors, checked_post_count=None, checked_job_count=None):
    with db() as conn:
        conn.execute(
            "INSERT INTO events(user_id, event_type, details) VALUES (?, ?, ?)",
            (
                user_id,
                "linkedin_sync",
                json.dumps(
                    {
                        "imported": imported,
                        "post_count": post_count,
                        "job_count": job_count,
                        "checked_post_count": post_count if checked_post_count is None else checked_post_count,
                        "checked_job_count": job_count if checked_job_count is None else checked_job_count,
                        "errors": errors[:5],
                    },
                    ensure_ascii=False,
                ),
            ),
        )


def sync_status(user_id):
    with db() as conn:
        row = conn.execute(
            "SELECT details, created_at FROM events WHERE user_id=? AND event_type='linkedin_sync' ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    if not row:
        return {"last_sync_at": "", "imported": 0, "post_count": 0, "job_count": 0, "errors": []}
    try:
        details = json.loads(row["details"] or "{}")
    except json.JSONDecodeError:
        details = {}
    details["last_sync_at"] = row["created_at"]
    return details


def linkedin_cursor(user_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM linkedin_cursors WHERE user_id=?", (user_id,)).fetchone()
        if row:
            return dict(row)
        conn.execute("INSERT INTO linkedin_cursors(user_id, job_start, content_start) VALUES (?, 0, 0)", (user_id,))
        return {"user_id": user_id, "job_start": 0, "content_start": 0}


def job_description_missing(lead):
    text = (lead.get("post_text") or "").strip().lower()
    if not text:
        return True
    missing_signals = (
        "detailed job description will appear",
        "could not read the full linkedin job description",
        "open the linkedin job page to view the complete description",
    )
    if any(signal in text for signal in missing_signals):
        return True
    useful = re.sub(r"location:\s*[^\n]+", "", text, flags=re.I).strip()
    return len(useful) < 80


def unavailable_job_match(lead):
    return {
        "overall_match_percentage": 0,
        "match_label": "Match unavailable",
        "summary": "HireMate needs the full job description before it can give a reliable profile match. Open the LinkedIn job page to review the complete details.",
        "matched_skills": [],
        "missing_skills": [],
        "matched_keywords": [],
        "unmatched_keywords": [],
        "strengths": [],
        "gaps": ["Full job description was not available during sync."],
        "generated_by": "description_unavailable",
    }


def save_linkedin_cursor(user_id, job_start, content_start=0):
    bounded_start = int(job_start or 0) % 200
    bounded_content = int(content_start or 0) % 200
    with db() as conn:
        conn.execute(
            """
            INSERT INTO linkedin_cursors(user_id, job_start, content_start, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
              job_start=excluded.job_start,
              content_start=excluded.content_start,
              updated_at=CURRENT_TIMESTAMP
            """,
            (user_id, bounded_start, bounded_content),
        )


def sync_until_new_leads(sync_user, user_id, start, keyword_offset=0):
    all_posts = []
    all_errors = []
    all_imported = []
    current_start = max(0, int(start or 0))
    pages_scanned = 0
    current_keyword_offset = max(0, int(keyword_offset or 0))
    include_posts = current_start == 0
    for _ in range(LINKEDIN_MAX_PAGES_PER_CLICK):
        posts, errors = sync_linkedin_for_profile(
            sync_user,
            job_start=current_start,
            include_posts=include_posts,
            keyword_offset=current_keyword_offset,
        )
        include_posts = False
        all_posts.extend(posts)
        all_errors.extend(errors)
        pages_scanned += 1
        imported = import_posts(user_id, posts) if posts else []
        all_imported.extend(imported)
        current_start += LINKEDIN_JOB_PAGE_STEP
        current_keyword_offset += 2
        if imported or not posts:
            break
    return all_posts, all_errors, all_imported, pages_scanned, current_start, current_keyword_offset


def sync_one_user(user):
    sync_user = dict(user)
    cipher = sync_user.get("linkedin_cookie_cipher") or ""
    sync_user["linkedin_cookie"] = reveal_text(cipher) if cipher else ""
    cursor = linkedin_cursor(user["id"])
    posts, errors, imported, _pages_scanned, next_start, next_keyword_offset = sync_until_new_leads(sync_user, user["id"], int(cursor.get("job_start") or 0), int(cursor.get("content_start") or 0))
    save_linkedin_cursor(user["id"], next_start, next_keyword_offset)
    post_count = len([p for p in imported if p.get("lead_kind") == "post"])
    job_count = len([p for p in imported if p.get("lead_kind") == "job"])
    checked_post_count = len([p for p in posts if p.get("lead_kind") == "post"])
    checked_job_count = len([p for p in posts if p.get("lead_kind") == "job"])
    record_sync_event(user["id"], len(imported), post_count, job_count, errors, checked_post_count=checked_post_count, checked_job_count=checked_job_count)
    if imported:
        try:
            notify_hot_leads(dict(user), imported)
        except Exception:
            pass
    try:
        maybe_send_daily_summary(dict(user))
    except Exception:
        pass
    return len(imported), post_count, job_count


def sync_public_posts_one_user(user):
    sync_user = dict(user)
    cipher = sync_user.get("linkedin_cookie_cipher") or ""
    sync_user["linkedin_cookie"] = reveal_text(cipher) if cipher else ""
    cursor = linkedin_cursor(user["id"])
    posts, errors, meta = collect_public_linkedin_posts(
        sync_user,
        keyword_offset=int(cursor.get("content_start") or 0),
        include_meta=True,
    )
    imported = import_posts(user["id"], posts) if posts else []
    keywords_used = meta.get("keywords_used", [])
    next_keyword_offset = int(cursor.get("content_start") or 0) + max(1, len(keywords_used))
    save_linkedin_cursor(user["id"], int(cursor.get("job_start") or 0), next_keyword_offset)
    post_count = len([p for p in imported if p.get("lead_kind") == "post"])
    if imported or posts:
        record_sync_event(
            user["id"],
            len(imported),
            post_count,
            0,
            errors,
            checked_post_count=len(posts),
            checked_job_count=0,
        )
    if imported:
        try:
            notify_hot_leads(dict(user), imported)
        except Exception:
            pass
    return len(imported), post_count, len(posts)


def auto_sync_loop():
    time.sleep(LINKEDIN_AUTO_SYNC_STARTUP_DELAY_SECONDS)
    loop_count = 0
    while True:
        loop_count += 1
        try:
            with db() as conn:
                users = [dict(row) for row in conn.execute("SELECT * FROM users WHERE is_active=1 AND linkedin_cookie_cipher IS NOT NULL AND linkedin_cookie_cipher <> ''").fetchall()]
            should_sync_posts = LINKEDIN_AUTO_POST_SYNC_EVERY > 0 and loop_count % LINKEDIN_AUTO_POST_SYNC_EVERY == 0
            for user in users:
                try:
                    imported, post_count, job_count = sync_one_user(user)
                    print(f"Auto LinkedIn sync user={user['id']} imported={imported} posts={post_count} jobs={job_count}")
                    if should_sync_posts:
                        post_imported, public_post_count, checked_posts = sync_public_posts_one_user(user)
                        print(f"Auto public post sync user={user['id']} imported={post_imported} posts={public_post_count} checked={checked_posts}")
                except Exception as exc:
                    record_sync_event(user["id"], 0, 0, 0, [str(exc)])
                    print(f"Auto LinkedIn sync failed for user={user['id']}: {exc}")
        except Exception as exc:
            print(f"Auto LinkedIn sync loop failed: {exc}")
        jitter = random.randint(0, LINKEDIN_AUTO_SYNC_JITTER_SECONDS)
        time.sleep(LINKEDIN_AUTO_SYNC_INTERVAL_SECONDS + jitter)


def analytics(user_id):
    with db() as conn:
        counts = conn.execute(
            """
            SELECT
              COUNT(*) total,
              SUM(CASE WHEN temperature='hot' THEN 1 ELSE 0 END) hot,
              SUM(CASE WHEN temperature='warm' THEN 1 ELSE 0 END) warm,
              SUM(CASE WHEN temperature='cold' THEN 1 ELSE 0 END) cold,
              SUM(CASE WHEN lead_kind='post' THEN 1 ELSE 0 END) posts,
              SUM(CASE WHEN lead_kind='job' THEN 1 ELSE 0 END) jobs
            FROM leads WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()
        draft_counts = conn.execute(
            """
            SELECT
              COUNT(*) total,
              SUM(CASE WHEN draft_type='message' THEN 1 ELSE 0 END) messages,
              SUM(CASE WHEN draft_type='comment' THEN 1 ELSE 0 END) comments,
              SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) approved,
              SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) pending
            FROM drafts WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()
        daily = conn.execute(
            """
            SELECT date(created_at) AS day,
              SUM(CASE WHEN temperature='hot' THEN 1 ELSE 0 END) hot,
              SUM(CASE WHEN temperature='warm' THEN 1 ELSE 0 END) warm,
              SUM(CASE WHEN temperature='cold' THEN 1 ELSE 0 END) cold
            FROM leads
            WHERE user_id=? AND date(created_at) >= date('now', '-6 day')
            GROUP BY date(created_at)
            ORDER BY day
            """,
            (user_id,),
        ).fetchall()
        skills = conn.execute("SELECT tags FROM leads WHERE user_id=? AND tags <> ''", (user_id,)).fetchall()
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        keyword_row = conn.execute(
            "SELECT response_json FROM ai_keyword_profiles WHERE user_id=? ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    top_skills = analytics_top_skills(dict(user) if user else {}, skills, keyword_row)
    return {
        "leads_discovered": counts["total"] or 0,
        "hot_leads": counts["hot"] or 0,
        "warm_leads": counts["warm"] or 0,
        "cold_leads": counts["cold"] or 0,
        "post_leads": counts["posts"] or 0,
        "job_leads": counts["jobs"] or 0,
        "drafts_total": draft_counts["total"] or 0,
        "drafts_messages": draft_counts["messages"] or 0,
        "drafts_comments": draft_counts["comments"] or 0,
        "drafts_pending": draft_counts["pending"] or 0,
        "drafts_approved": draft_counts["approved"] or 0,
        "daily": [dict(row) for row in daily],
        "top_skills": top_skills,
    }


def analytics_top_skills(user, lead_skill_rows, keyword_row):
    """Rank skills from profile data, cached AI keywords, and matched lead tags.

    The analytics page refreshes often, so this function reads cached AI keyword
    output instead of calling the AI provider on every page load.
    """
    weighted = {}
    labels = {}

    def add(value, weight):
        value = re.sub(r"\s+", " ", str(value or "")).strip(" -:;,.\n\t")
        if not value or len(value) > 80:
            return
        lowered = value.lower()
        blocked = {"hiring", "opportunity", "remote", "job", "jobs", "internship", "internships", "apply", "apply mentioned"}
        if lowered in blocked or "mentioned" in lowered:
            return
        key = analytics_skill_key(value)
        if not key:
            return
        weighted[key] = weighted.get(key, 0) + weight
        labels.setdefault(key, value)

    for field, weight in [("skills", 8), ("target_roles", 4), ("interests", 2)]:
        for item in split_simple_csv(user.get(field, "")):
            add(item, weight)

    keyword_profile = {}
    if keyword_row:
        try:
            keyword_profile = json.loads(keyword_row["response_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            keyword_profile = {}
    for field, weight in [("core_skills", 7), ("tools_and_libraries", 5), ("expanded_skills", 3), ("semantic_keywords", 2)]:
        values = keyword_profile.get(field, [])
        for item in values if isinstance(values, list) else []:
            add(item, weight)

    for row in lead_skill_rows:
        for tag in split_simple_csv(row["tags"] or ""):
            add(tag, 3)

    ranked = sorted(weighted.items(), key=lambda item: item[1], reverse=True)[:6]
    return [{"skill": labels[key], "count": score} for key, score in ranked]


def split_simple_csv(value):
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def analytics_skill_key(value):
    key = re.sub(r"\bjs\b", "", str(value or "").lower().replace(".js", ""))
    key = re.sub(r"[^a-z0-9+#]+", "", key)
    return key
def seed_demo_account():
    with db() as conn:
        row = conn.execute("SELECT id FROM users WHERE email=?", ("demo@hiremate.local",)).fetchone()
        if row:
            user_id = row["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO users(first_name, last_name, email, password_hash, headline, location, skills, interests, target_roles)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Demo",
                    "User",
                    "demo@hiremate.local",
                    hash_password("Demo@123"),
                    "Final year software engineering student",
                    "Islamabad, Pakistan",
                    "React, JavaScript, Python, Django, Node, CSS, HTML",
                    "Remote, Internship, Frontend, AI, Freelance",
                    "Frontend Developer, Python Developer",
                ),
            )
            user_id = cur.lastrowid
        count = conn.execute("SELECT COUNT(*) c FROM leads WHERE user_id=?", (user_id,)).fetchone()["c"]
    if count == 0:
        import_posts(user_id, sample_posts())


def ensure_admin_account():
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return
    with db() as conn:
        row = conn.execute("SELECT id FROM users WHERE lower(email)=lower(?)", (ADMIN_EMAIL,)).fetchone()
        if row:
            params = ["admin", 1]
            sql = "UPDATE users SET role=?, is_active=?"
            if ADMIN_PASSWORD:
                sql += ", password_hash=?"
                params.append(hash_password(ADMIN_PASSWORD))
            sql += " WHERE id=?"
            params.append(row["id"])
            conn.execute(sql, params)
            return
        first_name = os.getenv("ADMIN_FIRST_NAME", "HireMate").strip() or "HireMate"
        last_name = os.getenv("ADMIN_LAST_NAME", "Admin").strip() or "Admin"
        cur = conn.execute(
            """
            INSERT INTO users(first_name, last_name, email, password_hash, headline, role, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                first_name,
                last_name,
                ADMIN_EMAIL,
                hash_password(ADMIN_PASSWORD),
                "HireMate administrator",
                "admin",
                1,
            ),
        )
        conn.execute(
            "INSERT INTO events(user_id, event_type, details) VALUES (?, ?, ?)",
            (cur.lastrowid, "admin_account_ready", json.dumps({"source": "environment"}, ensure_ascii=False)),
        )


def _build_reset_link(token):
    """Build a full URL for the password reset page, detecting the current deployment origin."""
    # Check for explicit FRONTEND_URL or VERCEL_URL env vars first
    frontend_url = os.environ.get("FRONTEND_URL", "").strip().rstrip("/")
    if not frontend_url:
        vercel_url = os.environ.get("VERCEL_URL", "").strip()
        if vercel_url:
            frontend_url = f"https://{vercel_url}" if not vercel_url.startswith("http") else vercel_url
    if not frontend_url:
        frontend_url = f"http://localhost:{APP_PORT}"
    return f"{frontend_url}/reset-password.html?token={token}"


def _send_password_reset_email(user, reset_link):
    """Send a professional password reset email to the user."""
    from services.email_service import send_email

    first_name = user.get("first_name", "there")
    to_email = user["email"]
    subject = "Reset your HireMate password"

    text_body = (
        f"Hi {first_name},\n\n"
        f"We received a request to reset the password for your HireMate account.\n\n"
        f"Click the link below to set a new password:\n"
        f"{reset_link}\n\n"
        f"This link will expire in 1 hour for security reasons.\n\n"
        f"If you didn't request a password reset, you can safely ignore this email. "
        f"Your password will remain unchanged.\n\n"
        f"— The HireMate Team"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#0e1117;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0e1117;padding:40px 20px;">
<tr><td align="center">
<table width="480" cellpadding="0" cellspacing="0" style="background:#181c24;border-radius:16px;border:1px solid #2a2f3a;overflow:hidden;">
  <tr><td style="padding:32px 36px 24px;text-align:center;">
    <div style="display:inline-block;width:44px;height:44px;background:linear-gradient(135deg,#4affa0,#00c4ff);border-radius:12px;line-height:44px;font-size:22px;font-weight:800;color:#0e1117;font-family:'Segoe UI',Arial,sans-serif;margin-bottom:16px;">H</div>
    <h1 style="margin:0 0 4px;color:#f1f3f5;font-size:20px;font-weight:700;">Reset Your Password</h1>
    <p style="margin:0;color:#8b95a5;font-size:14px;">We received a request to reset your password.</p>
  </td></tr>
  <tr><td style="padding:0 36px 28px;">
    <p style="color:#c9cdd4;font-size:14px;line-height:1.6;margin:0 0 24px;">
      Hi <strong style="color:#f1f3f5;">{first_name}</strong>,<br><br>
      Click the button below to set a new password for your HireMate account. This link will expire in <strong style="color:#f1f3f5;">1 hour</strong>.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
      <a href="{reset_link}" style="display:inline-block;padding:14px 36px;background:linear-gradient(135deg,#4affa0,#00c4ff);color:#0e1117;font-size:15px;font-weight:700;text-decoration:none;border-radius:10px;">Reset Password</a>
    </td></tr></table>
    <p style="color:#8b95a5;font-size:12px;line-height:1.5;margin:24px 0 0;text-align:center;">
      If the button doesn't work, copy and paste this link into your browser:<br>
      <a href="{reset_link}" style="color:#4affa0;word-break:break-all;font-size:11px;">{reset_link}</a>
    </p>
  </td></tr>
  <tr><td style="padding:20px 36px;border-top:1px solid #2a2f3a;text-align:center;">
    <p style="margin:0;color:#5c6370;font-size:12px;line-height:1.5;">
      If you didn't request this, you can safely ignore this email.<br>
      Your password will remain unchanged.
    </p>
  </td></tr>
</table>
<p style="margin:24px 0 0;color:#3a3f4a;font-size:11px;text-align:center;">&copy; HireMate &mdash; Smart LinkedIn Lead Discovery</p>
</td></tr></table>
</body></html>"""

    send_email(to_email, subject, text_body, html_body)


def run():
    init_db()
    seed_demo_account()
    ensure_admin_account()
    if LINKEDIN_AUTO_SYNC_ENABLED:
        threading.Thread(target=auto_sync_loop, daemon=True).start()
    server = ThreadingHTTPServer((APP_HOST, APP_PORT), HireMateHandler)
    print(f"HireMate backend running at http://localhost:{APP_PORT}/landing.html")
    print("API health: http://localhost:8000/api/health")
    server.serve_forever()













