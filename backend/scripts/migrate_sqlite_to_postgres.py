"""Copy HireMate data from SQLite into PostgreSQL.

Usage:
  $env:DATABASE_URL="postgresql://user:password@localhost:5432/hiremate"
  python backend/scripts/migrate_sqlite_to_postgres.py
"""

import os
import sqlite3
import sys
from pathlib import Path

import psycopg2.extras


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from core.config import DATABASE_PATH  # noqa: E402
from core.database import init_db, postgres_connect  # noqa: E402


TABLES = [
    "users",
    "sessions",
    "leads",
    "drafts",
    "events",
    "linkedin_cursors",
    "ai_keyword_profiles",
    "ai_profile_matches",
    "notification_preferences",
    "email_notifications",
]


def sqlite_columns(conn, table):
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def postgres_columns(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return [row["column_name"] for row in cur.fetchall()]


def set_sequence(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT pg_get_serial_sequence(%s, 'id') seq
            """,
            (table,),
        )
        row = cur.fetchone()
        seq = row and row.get("seq")
        if not seq:
            return
        cur.execute(f"SELECT COALESCE(MAX(id), 0) max_id FROM {table}")
        max_id = int(cur.fetchone()["max_id"] or 0)
        cur.execute("SELECT setval(%s, %s, %s)", (seq, max_id, max_id > 0))


def copy_table(sqlite_conn, pg_conn, table):
    sqlite_cols = sqlite_columns(sqlite_conn, table)
    pg_cols = postgres_columns(pg_conn, table)
    cols = [col for col in sqlite_cols if col in pg_cols]
    if not cols:
        return 0
    rows = sqlite_conn.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
    if not rows:
        return 0
    quoted_cols = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    conflict = "id" if "id" in cols else ("user_id" if table in {"linkedin_cursors", "ai_keyword_profiles", "notification_preferences"} else "")
    on_conflict = f" ON CONFLICT ({conflict}) DO NOTHING" if conflict else ""
    sql = f"INSERT INTO {table} ({quoted_cols}) VALUES ({placeholders}){on_conflict}"
    values = [tuple(row[col] for col in cols) for row in rows]
    with pg_conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, values, page_size=200)
    pg_conn.commit()
    if "id" in cols:
        set_sequence(pg_conn, table)
        pg_conn.commit()
    return len(rows)


def main():
    if not os.getenv("DATABASE_URL", "").strip():
        raise SystemExit("Set DATABASE_URL first, for example postgresql://user:password@localhost:5432/hiremate")
    if not DATABASE_PATH.exists():
        raise SystemExit(f"SQLite database not found: {DATABASE_PATH}")
    init_db()
    sqlite_conn = sqlite3.connect(DATABASE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = postgres_connect()
    try:
        total = 0
        for table in TABLES:
            count = copy_table(sqlite_conn, pg_conn, table)
            total += count
            print(f"{table}: copied {count}")
        pg_conn.commit()
        print(f"Done. Copied {total} rows into PostgreSQL.")
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
