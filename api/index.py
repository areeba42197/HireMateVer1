import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import HireMateHandler, ensure_admin_account, seed_demo_account  # noqa: E402
from core.database import init_db  # noqa: E402


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
        if self.path.split("?", 1)[0] != "/api/health":
            ensure_database()

    def do_OPTIONS(self):
        self._prepare_vercel_request()
        return super().do_OPTIONS()

    def do_GET(self):
        self._prepare_vercel_request()
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
