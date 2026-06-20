"""Review API for the `suggested_tasks` staging table.

Staging/scratchpad only — these endpoints let a human review and edit proposed
ERP actions. They DO NOT call ERP and DO NOT create CRM records. The approve
endpoint only flips the approved flag; actual execution is a future, separate
step once the ERP client/applier exists.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database.connection import get_connection
from backend.database.repositories import suggested_tasks as repo
from backend.middleware.auth import require_auth

router = APIRouter(
    prefix="/api/suggested-tasks",
    tags=["suggested-tasks"],
    dependencies=[Depends(require_auth)],
)


class EditBody(BaseModel):
    task_type: str | None = None
    description: str | None = None
    payload: dict | None = None
    confidence: float | None = None
    evidence_quote: str | None = None


@router.get("/pending")
def list_pending():
    """Returns pending proposals with enough email context to identify the source
    in the list view (subject, sender) without a separate detail fetch."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT st.*,
                   e.subject        AS email_subject,
                   e.from_address   AS email_from,
                   e.from_name      AS email_from_name,
                   e.received_at    AS email_received_at
            FROM suggested_tasks st
            LEFT JOIN emails e ON e.id = st.email_id
            WHERE st.approved = 0 AND st.executed_at IS NULL
            ORDER BY st.sequence_order ASC, st.created_at ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _body_preview(email_row) -> str | None:
    """Returns body_preview if set, otherwise first 600 chars of body_text."""
    if not email_row:
        return None
    preview = email_row["body_preview"]
    if preview:
        return preview
    body = email_row["body_text"] or ""
    return (body[:600] + "…") if len(body) > 600 else (body or None)


@router.get("/{task_id:int}")
def get_one(task_id: int):
    """Returns the staged proposal enriched with source email context and the
    original AI suggestion context. No secrets are exposed."""
    conn = get_connection()
    try:
        row = repo.get(conn, task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="suggested_task not found")
        result = dict(row)

        # Source email context — safe fields only (no raw PII beyond what's in
        # the suggestion already, no IMAP credentials, no body_text raw dump)
        email = conn.execute(
            """SELECT id, subject, from_address, from_name, to_addresses,
                      cc_addresses, body_preview, body_text, received_at,
                      has_attachments, source
               FROM emails WHERE id = ?""",
            (row["email_id"],),
        ).fetchone()
        result["email_context"] = {
            "subject":        email["subject"] if email else None,
            "from_address":   email["from_address"] if email else None,
            "from_name":      email["from_name"] if email else None,
            "to_addresses":   email["to_addresses"] if email else None,
            "cc_addresses":   email["cc_addresses"] if email else None,
            "body_preview":   _body_preview(email),
            "received_at":    email["received_at"] if email else None,
            "has_attachments": bool(email["has_attachments"]) if email else False,
            "source":         email["source"] if email else None,
        }

        # AI suggestion context (classification pass results)
        suggestion = conn.execute(
            """SELECT id, category, suggested_action, reasoning, summary,
                      draft_subject, draft_to, draft_content, confidence_note
               FROM ai_suggestions WHERE id = ?""",
            (row["suggestion_id"],),
        ).fetchone()
        result["suggestion_context"] = dict(suggestion) if suggestion else None

        return result
    finally:
        conn.close()


@router.patch("/{task_id:int}")
def edit(task_id: int, body: EditBody):
    fields = body.model_dump(exclude_none=True)
    conn = get_connection()
    try:
        if repo.get(conn, task_id) is None:
            raise HTTPException(status_code=404, detail="suggested_task not found")
        repo.update(conn, task_id, fields)
        return dict(repo.get(conn, task_id))
    finally:
        conn.close()


@router.post("/{task_id:int}/reject")
def reject(task_id: int):
    conn = get_connection()
    try:
        if repo.get(conn, task_id) is None:
            raise HTTPException(status_code=404, detail="suggested_task not found")
        ok = repo.reject(conn, task_id)
        return {"rejected": ok}
    finally:
        conn.close()


@router.post("/{task_id:int}/approve")
def approve(task_id: int):
    """Flips approved=1 ONLY. Does not call ERP, does not create CRM records.
    Execution is a future, separate step."""
    conn = get_connection()
    try:
        if repo.get(conn, task_id) is None:
            raise HTTPException(status_code=404, detail="suggested_task not found")
        ok = repo.set_approved(conn, task_id)
        return {"approved": ok}
    finally:
        conn.close()
