import os
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import HireMateHandler, ensure_admin_account, json_response, seed_demo_account  # noqa: E402
from core.config import DATABASE_PATH, DATABASE_URL  # noqa: E402
from core.database import init_db, postgres_connect, postgres_release, using_postgres  # noqa: E402


_db_ready = False


def ensure_database():
    global _db_ready
    if _db_ready:
        return
    init_db()
    seed_demo_account()
    ensure_admin_account()
    _db_ready = True


class handler(HireMateHandler):
    def _prepare_vercel_request(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        hm_path = (query.pop("hm_path", [""])[0] or "").strip("/")
        if not hm_path and parsed.path.startswith("/api/"):
            hm_path = parsed.path[len("/api/"):].strip("/")
        if hm_path:
            self.path = "/api/" + hm_path
            if query:
                self.path += "?" + urlencode(query, doseq=True)
        if self.path.split("?", 1)[0] not in {"/api/health", "/api/debug/db-mode", "/api/debug/db-ping"}:
            ensure_database()

    def do_OPTIONS(self):
        self._prepare_vercel_request()
        return super().do_OPTIONS()

    def do_GET(self):
        self._prepare_vercel_request()
        if self.path.split("?", 1)[0] == "/api/debug/db-mode":
            db_host = ""
            if DATABASE_URL:
                db_host = urlparse(DATABASE_URL).hostname or ""
            return json_response(self, 200, {
                "ok": True,
                "mode": "postgres" if using_postgres() else "sqlite",
                "database_url_present": bool(DATABASE_URL),
                "database_host": db_host,
                "sqlite_path": "" if using_postgres() else str(DATABASE_PATH),
            })
        if self.path.split("?", 1)[0] == "/api/debug/db-ping":
            started = time.monotonic()
            try:
                if using_postgres():
                    conn = postgres_connect()
                    try:
                        with conn.cursor() as cur:
                            cur.execute("SELECT 1 AS ok")
                            row = cur.fetchone()
                        conn.rollback()
                    finally:
                        postgres_release(conn)
                    return json_response(self, 200, {
                        "ok": True,
                        "mode": "postgres",
                        "result": int(row["ok"]) if row else 0,
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                    })
                return json_response(self, 200, {
                    "ok": True,
                    "mode": "sqlite",
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                })
            except Exception as exc:
                return json_response(self, 503, {
                    "ok": False,
                    "mode": "postgres" if using_postgres() else "sqlite",
                    "error": str(exc),
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                })
        return super().do_GET()

    def do_POST(self):
        self._prepare_vercel_request()
        return super().do_POST()

    def do_PATCH(self):
        self._prepare_vercel_request()
        return super().do_PATCH()

    def do_DELETE(self):
        self._prepare_vercel_request()
        return super().do_DELETE()
