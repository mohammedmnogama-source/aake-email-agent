import sqlite3


def create(conn: sqlite3.Connection, data: dict) -> int:
    cursor = conn.execute(
        """
        INSERT INTO ai_suggestions (
            email_id, model_used, category, suggested_action, reasoning,
            summary,
            draft_subject, draft_to, draft_content, extracted_data,
            suggested_vendor_id, confidence_note, raw_response,
            prompt_tokens, completion_tokens, few_shot_count,
            needs_clarification, clarification_type, clarification_question,
            clarification_options, suggested_recipients, clarification_round,
            manually_handled
        ) VALUES (
            :email_id, :model_used, :category, :suggested_action, :reasoning,
            :summary,
            :draft_subject, :draft_to, :draft_content, :extracted_data,
            :suggested_vendor_id, :confidence_note, :raw_response,
            :prompt_tokens, :completion_tokens, :few_shot_count,
            :needs_clarification, :clarification_type, :clarification_question,
            :clarification_options, :suggested_recipients, :clarification_round,
            :manually_handled
        )
        """,
        data,
    )
    return cursor.lastrowid


def get_by_email_id(conn: sqlite3.Connection, email_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM ai_suggestions WHERE email_id = ?", (email_id,)
    ).fetchone()


def delete_by_email_id(conn: sqlite3.Connection, email_id: int) -> None:
    # Delete in FK order: actions_taken → decisions → clarification_responses → ai_suggestions
    conn.execute(
        "DELETE FROM actions_taken WHERE decision_id IN "
        "(SELECT id FROM decisions WHERE suggestion_id IN "
        " (SELECT id FROM ai_suggestions WHERE email_id = ?))", (email_id,)
    )
    conn.execute(
        "DELETE FROM decisions WHERE suggestion_id IN "
        "(SELECT id FROM ai_suggestions WHERE email_id = ?)", (email_id,)
    )
    conn.execute(
        "DELETE FROM clarification_responses WHERE email_id = ?", (email_id,)
    )
    conn.execute("DELETE FROM ai_suggestions WHERE email_id = ?", (email_id,))


def get_similar(
    conn: sqlite3.Connection, email_id: int, n: int = 20
) -> list[sqlite3.Row]:
    """
    Return up to n prior decisions ranked by similarity to the given email.
    Priority: (1) same sender domain, (2) same category, (3) subject keyword overlap.
    """
    email = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    if not email:
        return []

    from_addr = email["from_address"] or ""
    from_domain = from_addr.split("@")[-1] if "@" in from_addr else ""
    subject = email["subject"] or ""
    subject_words = [w for w in subject.lower().split() if len(w) > 3]
    keyword = f"%{subject_words[0]}%" if subject_words else "%"

    return conn.execute(
        """
        SELECT
            e.from_address,
            COALESCE(NULLIF(SUBSTR(e.from_address, INSTR(e.from_address,'@')+1),''), '') AS from_domain,
            e.subject AS subject_keywords,
            s.category,
            s.suggested_action,
            d.decision,
            d.rejection_reason,
            d.edit_notes
        FROM decisions d
        JOIN ai_suggestions s ON s.id = d.suggestion_id
        JOIN emails e ON e.id = d.email_id
        WHERE d.email_id != ?
        ORDER BY
            (INSTR(e.from_address, ?) > 0) DESC,
            (s.category = (
                SELECT category FROM ai_suggestions WHERE email_id = ? LIMIT 1
            )) DESC,
            (LOWER(e.subject) LIKE ?) DESC,
            d.decided_at DESC
        LIMIT ?
        """,
        (email_id, from_domain, email_id, keyword, n),
    ).fetchall()
