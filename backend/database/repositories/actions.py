import sqlite3


def create(
    conn: sqlite3.Connection,
    decision_id: int,
    email_id: int,
    action_type: str,
) -> int:
    cursor = conn.execute(
        """INSERT INTO actions_taken (decision_id, email_id, action_type, status)
           VALUES (?, ?, ?, 'pending')""",
        (decision_id, email_id, action_type),
    )
    return cursor.lastrowid


def update_status(
    conn: sqlite3.Connection,
    action_id: int,
    status: str,
    result_data: str | None = None,
    error_message: str | None = None,
) -> None:
    conn.execute(
        """UPDATE actions_taken
           SET status = ?, result_data = ?, error_message = ?, executed_at = datetime('now')
           WHERE id = ?""",
        (status, result_data, error_message, action_id),
    )


def list_by_date_range(
    conn: sqlite3.Connection,
    date_from: str,
    date_to: str,
    limit: int = 100,
) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT a.*, e.subject, e.from_address
           FROM actions_taken a
           JOIN emails e ON e.id = a.email_id
           WHERE a.executed_at BETWEEN ? AND ?
           ORDER BY a.executed_at DESC
           LIMIT ?""",
        (date_from, date_to, limit),
    ).fetchall()
