import sqlite3


def create(
    conn: sqlite3.Connection,
    email_id: int,
    suggestion_id: int,
    decision: str,
    edited_content: str | None = None,
    edited_subject: str | None = None,
    edited_to: str | None = None,
    rejection_reason: str | None = None,
    edit_notes: str | None = None,
) -> int:
    cursor = conn.execute(
        """INSERT INTO decisions
           (email_id, suggestion_id, decision, edited_content, edited_subject,
            edited_to, rejection_reason, edit_notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (email_id, suggestion_id, decision, edited_content, edited_subject,
         edited_to, rejection_reason, edit_notes),
    )
    return cursor.lastrowid


def get_by_email_id(conn: sqlite3.Connection, email_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM decisions WHERE email_id = ? ORDER BY id DESC LIMIT 1",
        (email_id,),
    ).fetchone()


def list_recent(conn: sqlite3.Connection, limit: int = 50, offset: int = 0) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT d.*, e.subject, e.from_address, e.received_at,
                  s.category, s.suggested_action
           FROM decisions d
           JOIN emails e ON e.id = d.email_id
           JOIN ai_suggestions s ON s.id = d.suggestion_id
           ORDER BY d.decided_at DESC
           LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()
