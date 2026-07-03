import sqlite3
from pathlib import Path

_DB_PATH: str | None = None


def init_db(database_path: str) -> None:
    global _DB_PATH
    _DB_PATH = database_path
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    _run_migrations()


def get_connection() -> sqlite3.Connection:
    if _DB_PATH is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _run_migrations() -> None:
    migrations_dir = Path(__file__).parent / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    # Bookkeeping table first.
    conn = get_connection()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _migrations "
            "(filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        conn.commit()
    finally:
        conn.close()

    for path in migration_files:
        # A FRESH connection per migration file. This matters when a migration
        # rewrites the schema via the `writable_schema` hack (see migration 020):
        # on the SAME connection that leaves SQLite's in-memory schema stale, so
        # the next migration's `ALTER TABLE ... ADD COLUMN` fails to re-parse
        # ("error in table ... after add column: near ... syntax error"). A new
        # connection re-reads the schema from disk, exactly as a later app
        # startup would. Each migration file is still atomic on its own
        # connection (its own executescript / commit; rollback on close if it
        # raises).
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT 1 FROM _migrations WHERE filename = ?", (path.name,)
            ).fetchone()
            if row:
                continue
            conn.executescript(path.read_text())
            conn.execute("INSERT INTO _migrations (filename) VALUES (?)", (path.name,))
            conn.commit()
            print(f"[db] Applied migration: {path.name}")
        finally:
            conn.close()
