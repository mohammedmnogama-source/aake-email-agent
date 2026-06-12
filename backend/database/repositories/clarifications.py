import sqlite3


def create(
    conn: sqlite3.Connection,
    suggestion_id: int,
    email_id: int,
    round_num: int,
    mo_answer: str,
) -> int:
    cursor = conn.execute(
        """INSERT INTO clarification_responses
           (suggestion_id, email_id, round, mo_answer)
           VALUES (?, ?, ?, ?)""",
        (suggestion_id, email_id, round_num, mo_answer),
    )
    return cursor.lastrowid


def get_rounds(conn: sqlite3.Connection, email_id: int) -> list[sqlite3.Row]:
    """Return all clarification rounds for an email, oldest first."""
    return conn.execute(
        """SELECT cr.round, s.clarification_question AS question, cr.mo_answer
           FROM clarification_responses cr
           JOIN ai_suggestions s ON s.id = cr.suggestion_id
           WHERE cr.email_id = ?
           ORDER BY cr.round ASC""",
        (email_id,),
    ).fetchall()


def get_by_suggestion(conn: sqlite3.Connection, suggestion_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM clarification_responses WHERE suggestion_id = ? ORDER BY id DESC LIMIT 1",
        (suggestion_id,),
    ).fetchone()
