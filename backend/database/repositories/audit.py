import hashlib
import sqlite3


def log_call(
    conn: sqlite3.Connection,
    model: str,
    purpose: str,
    prompt: str,
    response: str,
    redactions_count: int = 0,
    email_id: int | None = None,
) -> None:
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    conn.execute(
        """
        INSERT INTO api_audit_log
            (model, purpose, prompt_size, response_size, prompt_hash, redactions_count, email_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (model, purpose, len(prompt), len(response), prompt_hash, redactions_count, email_id),
    )
    conn.commit()


def list_recent(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM api_audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
