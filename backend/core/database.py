import sqlite3
import re
from contextlib import contextmanager

from .config import DATABASE_PATH, DATABASE_URL

try:
    import psycopg2
    import psycopg2.extras
    import psycopg2.pool
except ImportError:  # PostgreSQL is optional until DATABASE_URL is set.
    psycopg2 = None

POSTGRES_POOL = None
OLD_DEFAULT_SKILLS = "React, JavaScript, Python, Django, Node, CSS, HTML"
OLD_DEFAULT_INTERESTS = "Remote, Internship, Frontend, AI, Freelance"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  linkedin_cookie_cipher TEXT,
  linkedin_user_agent TEXT DEFAULT '',
  linkedin_accept_language TEXT DEFAULT '',
  headline TEXT DEFAULT '',
  location TEXT DEFAULT '',
  about TEXT DEFAULT '',
  skills TEXT DEFAULT '',
  interests TEXT DEFAULT '',
  target_roles TEXT DEFAULT '',
  preferred_locations TEXT DEFAULT '',
  work_modes TEXT DEFAULT '',
  experience_level TEXT DEFAULT '',
  education TEXT DEFAULT '',
  experience_detail TEXT DEFAULT '',
  avatar_image TEXT DEFAULT '',
  cover_image TEXT DEFAULT '',
  role TEXT DEFAULT 'user',
  is_active INTEGER DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  source TEXT DEFAULT 'linkedin',
  lead_kind TEXT DEFAULT 'post',
  source_post_id TEXT,
  company TEXT NOT NULL,
  role_title TEXT NOT NULL,
  author_name TEXT DEFAULT '',
  author_title TEXT DEFAULT '',
  post_text TEXT NOT NULL,
  post_url TEXT DEFAULT '',
  location TEXT DEFAULT '',
  work_type TEXT DEFAULT '',
  employment_type TEXT DEFAULT '',
  experience TEXT DEFAULT '',
  salary TEXT DEFAULT '',
  likes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  reposts INTEGER DEFAULT 0,
  posted_at TEXT DEFAULT CURRENT_TIMESTAMP,
  score INTEGER DEFAULT 0,
  temperature TEXT DEFAULT 'cold',
  status TEXT DEFAULT 'new',
  tags TEXT DEFAULT '',
  comments_json TEXT DEFAULT '[]',
  reactions_json TEXT DEFAULT '{}',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, source_post_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  lead_id INTEGER NOT NULL,
  draft_type TEXT NOT NULL CHECK(draft_type IN ('message', 'comment')),
  tone TEXT NOT NULL,
  content TEXT NOT NULL,
  status TEXT DEFAULT 'pending',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  event_type TEXT NOT NULL,
  details TEXT DEFAULT '',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS linkedin_cursors (
  user_id INTEGER PRIMARY KEY,
  job_start INTEGER DEFAULT 0,
  content_start INTEGER DEFAULT 0,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_keyword_profiles (
  user_id INTEGER PRIMARY KEY,
  profile_hash TEXT NOT NULL,
  response_json TEXT NOT NULL,
  generated_by TEXT DEFAULT 'fallback',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_profile_matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  lead_id INTEGER NOT NULL,
  cache_key TEXT NOT NULL,
  response_json TEXT NOT NULL,
  generated_by TEXT DEFAULT 'fallback',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, lead_id, cache_key),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notification_preferences (
  user_id INTEGER PRIMARY KEY,
  hot_lead_alerts INTEGER DEFAULT 1,
  daily_summary INTEGER DEFAULT 1,
  draft_confirmations INTEGER DEFAULT 1,
  last_daily_summary_at TEXT DEFAULT '',
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS email_notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  notification_type TEXT NOT NULL,
  recipient_email TEXT NOT NULL,
  subject TEXT NOT NULL,
  status TEXT NOT NULL,
  error TEXT DEFAULT '',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  token TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  used INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_leads_user_created ON leads(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_leads_user_kind_created ON leads(user_id, lead_kind, created_at);
CREATE INDEX IF NOT EXISTS idx_leads_user_status_created ON leads(user_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_leads_user_temperature_created ON leads(user_id, temperature, created_at);
CREATE INDEX IF NOT EXISTS idx_drafts_user_status_updated ON drafts(user_id, status, updated_at);
CREATE INDEX IF NOT EXISTS idx_matches_user_updated ON ai_profile_matches(user_id, lead_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_sessions_token_expires ON sessions(token, expires_at);
"""

MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN about TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN target_roles TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN preferred_locations TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN work_modes TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN experience_level TEXT DEFAULT ''",
    "ALTER TABLE leads ADD COLUMN lead_kind TEXT DEFAULT 'post'",
    "ALTER TABLE leads ADD COLUMN comments_json TEXT DEFAULT '[]'",
    "ALTER TABLE leads ADD COLUMN reactions_json TEXT DEFAULT '{}'",
    "ALTER TABLE users ADD COLUMN linkedin_user_agent TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN linkedin_accept_language TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN education TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN experience_detail TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN avatar_image TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN cover_image TEXT DEFAULT ''",
    "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'",
    "ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1",
    "ALTER TABLE users ALTER COLUMN skills SET DEFAULT ''",
    "ALTER TABLE users ALTER COLUMN interests SET DEFAULT ''",
    """CREATE TABLE IF NOT EXISTS ai_profile_matches (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      lead_id INTEGER NOT NULL,
      cache_key TEXT NOT NULL,
      response_json TEXT NOT NULL,
      generated_by TEXT DEFAULT 'fallback',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(user_id, lead_id, cache_key),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS notification_preferences (
      user_id INTEGER PRIMARY KEY,
      hot_lead_alerts INTEGER DEFAULT 1,
      daily_summary INTEGER DEFAULT 1,
      draft_confirmations INTEGER DEFAULT 1,
      last_daily_summary_at TEXT DEFAULT '',
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )""",
    "ALTER TABLE notification_preferences ADD COLUMN last_daily_summary_at TEXT DEFAULT ''",
    """CREATE TABLE IF NOT EXISTS email_notifications (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER,
      notification_type TEXT NOT NULL,
      recipient_email TEXT NOT NULL,
      subject TEXT NOT NULL,
      status TEXT NOT NULL,
      error TEXT DEFAULT '',
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    )""",
    """CREATE TABLE IF NOT EXISTS password_reset_tokens (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      token TEXT NOT NULL UNIQUE,
      expires_at TEXT NOT NULL,
      used INTEGER DEFAULT 0,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )""",
]


def init_db():
    if using_postgres():
        conn = postgres_connect()
        try:
            run_postgres_schema(conn)
            run_postgres_migrations(conn)
            cleanup_old_profile_defaults_postgres(conn)
        finally:
            postgres_release(conn)
        return
    init_sqlite_db()


@contextmanager
def db():
    if using_postgres():
        conn = postgres_connect()
        try:
            yield PostgresConnection(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            postgres_release(conn)
        return
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row):
    return dict(row) if row is not None else None


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


def using_postgres():
    return DATABASE_URL.lower().startswith(("postgres://", "postgresql://"))


def init_sqlite_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.executescript(SCHEMA)
        for sql in MIGRATIONS:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass
        cleanup_old_profile_defaults_sqlite(conn)
        conn.commit()


def cleanup_old_profile_defaults_sqlite(conn):
    conn.execute(
        """
        UPDATE users
        SET skills='', interests=''
        WHERE skills=? AND interests=?
          AND COALESCE(headline, '')=''
          AND COALESCE(about, '')=''
          AND COALESCE(target_roles, '')=''
          AND COALESCE(education, '')=''
          AND COALESCE(experience_detail, '')=''
        """,
        (OLD_DEFAULT_SKILLS, OLD_DEFAULT_INTERESTS),
    )


def postgres_connect():
    global POSTGRES_POOL
    if psycopg2 is None:
        raise RuntimeError("PostgreSQL mode needs psycopg2. Install it with: pip install psycopg2-binary")
    if POSTGRES_POOL is None:
        POSTGRES_POOL = psycopg2.pool.ThreadedConnectionPool(
            1,
            20,
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
    return POSTGRES_POOL.getconn()


def postgres_release(conn):
    if POSTGRES_POOL is None:
        conn.close()
        return
    POSTGRES_POOL.putconn(conn)


def postgres_sql(sql):
    sql = sql.strip()
    if not sql:
        return ""
    if sql.upper().startswith("PRAGMA "):
        return ""
    sql = sql.replace("PRAGMA foreign_keys = ON;", "")
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    sql = sql.replace("INSERT OR IGNORE", "INSERT")
    sql = sql.replace("date('now', '-6 day')", "(CURRENT_DATE - INTERVAL '6 day')")
    sql = sql.replace("datetime('now', '-1 day')", "(CURRENT_TIMESTAMP - INTERVAL '1 day')")
    sql = sql.replace("datetime('now')", "CURRENT_TIMESTAMP")
    sql = re.sub(r"date\((created_at|updated_at|posted_at)\)", r"CAST(\1 AS date)", sql)
    sql = re.sub(r"datetime\(([^)]+)\)", r"CAST(\1 AS timestamp)", sql)
    param_token = "__HIREMATE_SQL_PARAM__"
    sql = sql.replace("?", param_token)
    sql = sql.replace("%", "%%")
    sql = sql.replace(param_token, "%s")
    return sql


def split_sql_script(script):
    parts = []
    current = []
    in_single = False
    in_double = False
    for ch in script:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == ";" and not in_single and not in_double:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def run_postgres_schema(conn):
    with conn.cursor() as cur:
        for statement in split_sql_script(SCHEMA):
            sql = postgres_sql(statement)
            if sql:
                cur.execute(sql)
    conn.commit()


def run_postgres_migrations(conn):
    with conn.cursor() as cur:
        cur.execute("SET lock_timeout TO '2s'")
        cur.execute("SET statement_timeout TO '8s'")
        conn.commit()
        for statement in MIGRATIONS:
            try:
                cur.execute(postgres_sql(statement))
                conn.commit()
            except Exception:
                conn.rollback()
        try:
            cur.execute("RESET lock_timeout")
            cur.execute("RESET statement_timeout")
            conn.commit()
        except Exception:
            conn.rollback()


def cleanup_old_profile_defaults_postgres(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE users
            SET skills='', interests=''
            WHERE skills=%s AND interests=%s
              AND COALESCE(headline, '')=''
              AND COALESCE(about, '')=''
              AND COALESCE(target_roles, '')=''
              AND COALESCE(education, '')=''
              AND COALESCE(experience_detail, '')=''
            """,
            (OLD_DEFAULT_SKILLS, OLD_DEFAULT_INTERESTS),
        )
    conn.commit()


class PostgresCursor:
    def __init__(self, cursor):
        self.cursor = cursor
        self.lastrowid = None

    def execute(self, sql, params=None):
        sql = postgres_sql(sql)
        lowered = sql.lstrip().lower()
        capture_id = (
            lowered.startswith("insert into users")
            or lowered.startswith("insert into drafts")
        ) and " returning " not in lowered
        if capture_id:
            sql = sql.rstrip().rstrip(";") + " RETURNING id"
        self.cursor.execute(sql, params or ())
        if capture_id:
            row = self.cursor.fetchone()
            self.lastrowid = row["id"] if row else None
        return self

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __iter__(self):
        return iter(self.cursor)


class PostgresConnection:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        cur = PostgresCursor(self.conn.cursor())
        return cur.execute(sql, params)

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()
