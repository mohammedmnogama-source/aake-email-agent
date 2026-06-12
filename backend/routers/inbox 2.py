"""
Inbox endpoints.

POST /api/inbox/sync      — fetch new emails + analyze them
POST /api/inbox/backfill  — one-time: read all sent emails + index everything to ChromaDB
GET  /api/inbox           — list all emails and their AI suggestions
GET  /api/inbox/{id}      — full detail for one email (with AI suggestion)
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.post("/sync")
def sync_inbox():
    """
    Fetch new emails from IMAP, then analyze any pending ones.
    Call this whenever you want to check for new emails.
    """
    from backend.email.fetcher import fetch_new_emails
    from backend.ai.analyzer import analyze_pending

    # Step 1: fetch from IMAP
    new_email_ids = fetch_new_emails()

    # Step 2: analyze whatever is pending (includes anything from previous runs too)
    analyzed_ids = analyze_pending()

    return {
        "fetched": len(new_email_ids),
        "analyzed": len(analyzed_ids),
        "new_email_ids": new_email_ids,
        "analyzed_ids": analyzed_ids,
    }


@router.post("/backfill")
def backfill():
    """
    One-time job: read ALL your sent emails from IMAP + index existing inbox emails.
    This is how the agent learns from your email history before any new emails arrive.
    Safe to run multiple times — already-indexed emails are skipped.
    """
    from backend.rag.store import backfill_existing_emails, backfill_sent_folder
    from backend.database.connection import get_connection

    conn = get_connection()
    try:
        inbox_count = backfill_existing_emails(conn)
        sent_count = backfill_sent_folder(conn)
    finally:
        conn.close()

    return {
        "inbox_emails_indexed": inbox_count,
        "sent_emails_indexed": sent_count,
        "message": f"Indexed {inbox_count} inbox + {sent_count} sent emails into ChromaDB",
    }


@router.get("")
def list_emails(status: str = None, limit: int = 50):
    """
    List all emails in the database.

    Optional filter: ?status=pending  or  ?status=decided  etc.

    Each item includes the AI suggestion if one exists.
    """
    from backend.database.connection import get_connection

    conn = get_connection()
    try:
        if status:
            rows = conn.execute(
                "SELECT e.id, e.subject, e.from_address, e.from_name, e.body_preview, "
                "e.received_at, e.fetched_at, e.status, e.source, "
                "s.category, s.suggested_action, s.summary, s.draft_content "
                "FROM emails e "
                "LEFT JOIN ai_suggestions s ON s.email_id = e.id "
                "WHERE e.status = ? "
                "ORDER BY e.id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT e.id, e.subject, e.from_address, e.from_name, e.body_preview, "
                "e.received_at, e.fetched_at, e.status, e.source, "
                "s.category, s.suggested_action, s.summary, s.draft_content "
                "FROM emails e "
                "LEFT JOIN ai_suggestions s ON s.email_id = e.id "
                "ORDER BY e.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows]


@router.get("/{email_id}")
def get_email(email_id: int):
    """
    Full detail for one email: the email itself + the AI suggestion + draft reply.
    """
    from backend.database.connection import get_connection

    conn = get_connection()
    try:
        email = conn.execute(
            "SELECT * FROM emails WHERE id = ?", (email_id,)
        ).fetchone()
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")

        suggestion = conn.execute(
            "SELECT * FROM ai_suggestions WHERE email_id = ?", (email_id,)
        ).fetchone()
    finally:
        conn.close()

    return {
        "email": dict(email),
        "suggestion": dict(suggestion) if suggestion else None,
    }
