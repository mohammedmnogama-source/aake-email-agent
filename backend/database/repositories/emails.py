import sqlite3
from typing import Any


def get_by_id(conn: sqlite3.Connection, email_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()


def get_by_imap_uid(
    conn: sqlite3.Connection, imap_uid: int, folder_path: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM emails WHERE imap_uid = ? AND folder_path = ?",
        (imap_uid, folder_path),
    ).fetchone()


def list_pending(
    conn: sqlite3.Connection, limit: int = 50, offset: int = 0
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM emails WHERE status = 'pending' "
        "ORDER BY received_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()


def list_by_status(
    conn: sqlite3.Connection,
    status: str,
    limit: int = 50,
    offset: int = 0,
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM emails WHERE status = ? ORDER BY received_at DESC LIMIT ? OFFSET ?",
        (status, limit, offset),
    ).fetchall()


def count_pending(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM emails WHERE status = 'pending'").fetchone()
    return row[0] if row else 0


def update_status(conn: sqlite3.Connection, email_id: int, status: str) -> None:
    conn.execute("UPDATE emails SET status = ? WHERE id = ?", (status, email_id))
