import sqlite3

from backend.email.style_learner import MAX_STYLE_EXAMPLES


def save_profile(
    conn: sqlite3.Connection,
    profile_json: str,
    email_count: int,
    confirmed: int = 0,
) -> None:
    # Insert new profile first, then trim to 2 most recent (newest=active, second=backup)
    conn.execute(
        """INSERT INTO writing_style (profile_json, email_count, confirmed, updated_at)
           VALUES (?, ?, ?, datetime('now'))""",
        (profile_json, email_count, confirmed),
    )
    conn.execute(
        """DELETE FROM writing_style WHERE id NOT IN
           (SELECT id FROM writing_style ORDER BY id DESC LIMIT 2)"""
    )
    conn.execute(
        "UPDATE settings SET value = ? WHERE key = 'style_email_count'",
        (str(email_count),),
    )
    conn.execute(
        "UPDATE settings SET value = ? WHERE key = 'style_confirmed'",
        (str(confirmed),),
    )
    if confirmed:
        conn.execute(
            "UPDATE settings SET value = datetime('now') WHERE key = 'style_last_updated'"
        )


def get_profile(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM writing_style ORDER BY id DESC LIMIT 1"
    ).fetchone()


def confirm_profile(conn: sqlite3.Connection) -> None:
    # Target only the newest profile row — leaves any backup row unconfirmed
    conn.execute(
        "UPDATE writing_style SET confirmed = 1 WHERE id = (SELECT MAX(id) FROM writing_style)"
    )
    conn.execute("UPDATE settings SET value = '1' WHERE key = 'style_confirmed'")
    conn.execute(
        "UPDATE settings SET value = datetime('now') WHERE key = 'style_last_updated'"
    )


def save_examples(conn: sqlite3.Connection, examples: list[dict]) -> None:
    # SAVEPOINT makes clear+insert atomic: if any insert fails, old examples are restored
    conn.execute("SAVEPOINT save_examples_sp")
    try:
        clear_examples(conn)
        for ex in examples[:MAX_STYLE_EXAMPLES]:
            conn.execute(
                """INSERT INTO style_examples (subject, body_preview, body_full, context_type)
                   VALUES (:subject, :body_preview, :body_full, :context_type)""",
                ex,
            )
        conn.execute("RELEASE save_examples_sp")
    except Exception:
        conn.execute("ROLLBACK TO save_examples_sp")
        raise


def get_examples(conn: sqlite3.Connection, limit: int = 5) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM style_examples ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


def clear_examples(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM style_examples")
