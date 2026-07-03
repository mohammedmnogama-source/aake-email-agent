"""Review + execute API for the `suggested_tasks` staging table.

Review endpoints let a human review, edit, approve or reject proposed ERP
actions — none of those call ERP. The separate, human-triggered `execute`
endpoint is the ONLY place that pushes an approved create_task to the ERP, via
an atomic claim + attempt fence so repeated/concurrent clicks and retries can
never create duplicate ERP tasks.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database.connection import get_connection
from backend.database.repositories import suggested_tasks as repo
from backend.database.repositories.suggested_tasks import NotEditableError
from backend.integrations import erp_client
from backend.integrations.erp_client import ErpConfigError, ErpError, build_task_payload
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


@router.get("/approved")
def list_approved():
    """Approved proposals (approved=1) in any execution state, newest first, with
    an `execution_is_stale` flag so the UI knows when an `executing` row may be
    re-triggered. This is the list the Execute action operates on."""
    conn = get_connection()
    try:
        return [dict(r) for r in repo.list_approved(conn)]
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
    """Edit content. Rejected (409) for executing/executed rows. A successful
    edit also resets the row to pending approval (see repo.update)."""
    fields = body.model_dump(exclude_none=True)
    conn = get_connection()
    try:
        if repo.get(conn, task_id) is None:
            raise HTTPException(status_code=404, detail="suggested_task not found")
        try:
            repo.update(conn, task_id, fields)
        except NotEditableError as e:
            raise HTTPException(status_code=409, detail=str(e))
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
    Rejects executing/executed rows. Execution is a separate endpoint."""
    conn = get_connection()
    try:
        if repo.get(conn, task_id) is None:
            raise HTTPException(status_code=404, detail="suggested_task not found")
        ok = repo.set_approved(conn, task_id)
        return {"approved": ok}
    finally:
        conn.close()


@router.post("/{task_id:int}/execute")
def execute(task_id: int):
    """Human-triggered ERP Create Task. The ONLY endpoint that calls the ERP.

    Approval never routes here. Uses an atomic claim + attempt fence so repeated
    clicks, concurrent clicks, retries and timeouts cannot create duplicate ERP
    tasks. Already-executed rows return the stored ERP UUID without a network
    call. Never retries automatically.
    """
    conn = get_connection()
    try:
        row = repo.get(conn, task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="suggested_task not found")
        if row["task_type"] != "create_task":
            raise HTTPException(status_code=400, detail="Only create_task suggestions can be executed")
        if row["approved"] == -1:
            raise HTTPException(status_code=400, detail="Rejected suggestion cannot be executed")
        if row["approved"] != 1:
            raise HTTPException(status_code=400, detail="Suggestion must be approved before execution")

        # Already executed -> idempotent success, no ERP call.
        if row["executed_at"] is not None:
            if row["erp_reference"]:
                return {"status": "executed", "erp_reference": row["erp_reference"], "duplicate": False}
            raise HTTPException(status_code=409, detail="Executed row is missing an ERP reference; manual review required")

        # A fresh (non-stale) claim held by another worker -> in progress.
        if row["execution_status"] == "executing" and not repo.is_stale_claim(row, conn):
            raise HTTPException(status_code=409, detail="Execution already in progress")

        claimed = repo.claim_execution(conn, task_id)
        if claimed is None:
            fresh = repo.get(conn, task_id)
            if fresh and fresh["executed_at"] and fresh["erp_reference"]:
                return {"status": "executed", "erp_reference": fresh["erp_reference"], "duplicate": False}
            raise HTTPException(status_code=409, detail="Execution already in progress")

        claimed_row, attempt_id = claimed
        body = build_task_payload(dict(claimed_row))

        try:
            result = erp_client.create_task(body)
        except ErpConfigError:
            repo.mark_failed(conn, task_id, attempt_id, "ERP integration is not configured")
            raise HTTPException(status_code=503, detail="ERP integration is not configured")
        except ErpError as e:
            repo.mark_failed(conn, task_id, attempt_id, str(e))
            raise HTTPException(status_code=502, detail=f"ERP task creation failed: {e}")

        # Fresh success and duplicate=true reconcile identically. The fence
        # ensures only this attempt writes; if a newer attempt reclaimed the row
        # meanwhile, its idempotent result already holds (same agent key).
        won = repo.reconcile_executed(conn, task_id, attempt_id, result["id"])
        if not won:
            # A newer attempt reclaimed this row while our ERP call was in flight.
            # Thanks to the shared agent_suggestion_key the ERP result is the same
            # task; prefer the row's stored reference, else our own valid id.
            fresh = repo.get(conn, task_id)
            ref = (fresh["erp_reference"] if fresh else None) or result["id"]
            return {"status": "executed", "erp_reference": ref, "duplicate": result["duplicate"]}
        return {"status": "executed", "erp_reference": result["id"], "duplicate": result["duplicate"]}
    finally:
        conn.close()
