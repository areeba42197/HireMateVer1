import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent
ENV_PATH = BASE_DIR / ".env"


def load_env_file(path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(ENV_PATH)

DATABASE_PATH = BASE_DIR / "data" / "hiremate.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SECURE_DIR = BASE_DIR / "secure"
XAI_KEY_FILE = SECURE_DIR / "xai_api_key.txt"
GROQ_KEY_FILE = SECURE_DIR / "groq_api_key.txt"

APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("PORT") or os.getenv("APP_PORT", "8000"))
APP_NAME = "HireMate API"

# Change this before real deployment. It is used for local token signing and
# reversible cookie protection in this FYP prototype.
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-local-development-secret")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_PIN = os.getenv("ADMIN_PIN", "7391").strip()

# Conservative LinkedIn collection limits for academic/local testing.
# Small batches and random delays reduce load and make failures easier to audit.
LINKEDIN_MAX_RESULTS_PER_SYNC = 8
LINKEDIN_MAX_SEARCH_QUERIES = 2
LINKEDIN_MIN_DELAY_SECONDS = 1
LINKEDIN_MAX_DELAY_SECONDS = 3
LINKEDIN_AUTO_SYNC_ENABLED = True
LINKEDIN_AUTO_SYNC_INTERVAL_SECONDS = 20 * 60
LINKEDIN_AUTO_SYNC_JITTER_SECONDS = 8 * 60
LINKEDIN_AUTO_SYNC_STARTUP_DELAY_SECONDS = 30
LINKEDIN_AUTO_POST_SYNC_EVERY = 3

# AI keyword generation. Keep keys outside frontend files. The app supports
# Groq first, and keeps xAI/Grok as a backward-compatible option.
AI_PROVIDER = os.getenv("AI_PROVIDER", "auto").strip().lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_CHAT_COMPLETIONS_URL = os.getenv("GROQ_CHAT_COMPLETIONS_URL", "https://api.groq.com/openai/v1/chat/completions")
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
XAI_MODEL = os.getenv("XAI_MODEL", "grok-4.20-reasoning")
XAI_CHAT_COMPLETIONS_URL = os.getenv("XAI_CHAT_COMPLETIONS_URL", "https://api.x.ai/v1/chat/completions")
AI_KEYWORD_CACHE_HOURS = int(os.getenv("AI_KEYWORD_CACHE_HOURS", "24"))

# Email notifications. Configure these before real email delivery.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_PASSWORD_FILE = SECURE_DIR / "smtp_password.txt"
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "HireMate")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").strip().lower() not in {"0", "false", "no"}

ALLOWED_STATIC_EXTENSIONS = {
    ".html",
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
}
