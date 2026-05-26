"""Remove navigation text accidentally imported as a LinkedIn post."""

import sqlite3
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def main():
    conn = sqlite3.connect(BACKEND_DIR / "data" / "hiremate.db")
    cur = conn.execute(
        """
        DELETE FROM leads
        WHERE lead_kind='post'
          AND company IN ('0 notifications', 'Home', 'Posts')
        """
    )
    conn.commit()
    conn.close()
    print(f"removed {cur.rowcount}")


if __name__ == "__main__":
    main()
