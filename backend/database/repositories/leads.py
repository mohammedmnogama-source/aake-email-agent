import sqlite3


def create(
    conn: sqlite3.Connection,
    email_id: int,
    action_id: int | None,
    extracted: dict,
    raw_extracted: str | None = None,
) -> int:
    cursor = conn.execute(
        """INSERT INTO leads
           (email_id, action_id, name, company, contact_email, contact_phone,
            request_summary, raw_extracted, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new')""",
        (
            email_id,
            action_id,
            extracted.get("name"),
            extracted.get("company"),
            extracted.get("contact_email"),
            extracted.get("contact_phone"),
            extracted.get("request_summary"),
            raw_extracted,
        ),
    )
    return cursor.lastrowid


def list_all(
    conn: sqlite3.Connection,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[sqlite3.Row]:
    if status:
        return conn.execute(
            """SELECT l.*, e.subject, e.received_at FROM leads l
               JOIN emails e ON e.id = l.email_id
               WHERE l.status = ?
               ORDER BY l.created_at DESC LIMIT ? OFFSET ?""",
            (status, limit, offset),
        ).fetchall()
    return conn.execute(
        """SELECT l.*, e.subject, e.received_at FROM leads l
           JOIN emails e ON e.id = l.email_id
           ORDER BY l.created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    ).fetchall()


def update_status(
    conn: sqlite3.Connection,
    lead_id: int,
    status: str,
    notes: str | None = None,
) -> None:
    conn.execute(
        "UPDATE leads SET status = ?, notes = ?, updated_at = datetime('now') WHERE id = ?",
        (status, notes, lead_id),
    )
