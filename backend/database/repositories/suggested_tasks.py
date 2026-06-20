"""Repository for the `suggested_tasks` staging table.

IMPORTANT: this is a STAGING / SCRATCHPAD layer only. ERP/Supabase remains the
real CRM and system of record. Nothing here calls ERP or writes CRM records —
it only stores *proposed* actions for human review, and (later) records the
result of an ERP call that some other code performs after approval.

State convention (kept inside existing columns — no new columns/tables):
    approved =  0  -> pending review   (the default)
    approved =  1  -> approved, NOT yet executed   (does NOT call ERP)
    approved = -1  -> rejected / dismissed
    executed_at IS NOT NULL  -> already executed against ERP (terminal)
"""

import json
import sqlite3


class AlreadyExecutedError(Exception):
    """Raised when trying to execute a proposal whose executed_at is already set."""


# Fields a human is allowed to edit via update(). Deliberately excludes
# approved, executed_at, erp_reference, error_message — those are state, not
# user-editable content.
_EDITABLE_FIELDS = {"task_type", "description", "payload", "confidence", "evidence_quote"}


def create(conn: sqlite3.Connection, data: dict) -> int:
    """Insert a new staged proposal. Returns its id.

    Required keys: email_id, suggestion_id, task_type, description.
    Optional: payload (dict -> stored as JSON, or str), confidence (float),
    evidence_quote (str), sequence_order (int).
    """
    payload = data.get("payload")
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)

    cursor = conn.execute(
        """
        INSERT INTO suggested_tasks (
            email_id, suggestion_id, sequence_order, task_type, description,
            payload, confidence, evidence_quote
        ) VALUES (
            :email_id, :suggestion_id, :sequence_order, :task_type, :description,
            :payload, :confidence, :evidence_quote
        )
        """,
        {
            "email_id": data["email_id"],
            "suggestion_id": data["suggestion_id"],
            "sequence_order": data.get("sequence_order", 0),
            "task_type": data["task_type"],
            "description": data["description"],
            "payload": payload,
            "confidence": data.get("confidence"),
            "evidence_quote": data.get("evidence_quote"),
        },
    )
    conn.commit()
    return cursor.lastrowid


def list_pending(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Proposals still awaiting review: not approved/rejected and not executed."""
    return conn.execute(
        """
        SELECT * FROM suggested_tasks
        WHERE approved = 0 AND executed_at IS NULL
        ORDER BY sequence_order ASC, created_at ASC
        """
    ).fetchall()


def get(conn: sqlite3.Connection, task_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM suggested_tasks WHERE id = ?", (task_id,)
    ).fetchone()


def exists_similar(
    conn: sqlite3.Connection, email_id: int, suggestion_id: int, task_type: str
) -> bool:
    """Duplicate-prevention check: True if a staged row already exists for the
    same (email_id, suggestion_id, task_type). Read-only."""
    row = conn.execute(
        """
        SELECT 1 FROM suggested_tasks
        WHERE email_id = ? AND suggestion_id = ? AND task_type = ?
        LIMIT 1
        """,
        (email_id, suggestion_id, task_type),
    ).fetchone()
    return row is not None


def update(conn: sqlite3.Connection, task_id: int, fields: dict) -> bool:
    """Edit human-editable content (description/payload/confidence/etc.).
    Ignores any non-editable keys. Returns True if a row was updated."""
    payload = fields.get("payload")
    if isinstance(payload, (dict, list)):
        fields = {**fields, "payload": json.dumps(payload)}

    clean = {k: v for k, v in fields.items() if k in _EDITABLE_FIELDS}
    if not clean:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in clean)
    values = list(clean.values()) + [task_id]
    cur = conn.execute(
        f"UPDATE suggested_tasks SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    return cur.rowcount > 0


def reject(conn: sqlite3.Connection, task_id: int) -> bool:
    """Soft-reject / dismiss a proposal (approved = -1). Keeps the row for
    audit instead of deleting. No effect on already-executed rows."""
    cur = conn.execute(
        "UPDATE suggested_tasks SET approved = -1 WHERE id = ? AND executed_at IS NULL",
        (task_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def set_approved(conn: sqlite3.Connection, task_id: int) -> bool:
    """Mark a proposal approved (approved = 1). This ONLY flips the flag — it
    does NOT call ERP and does NOT create any CRM record. A future, separate
    applier is responsible for actually executing it. Won't touch rejected or
    already-executed rows."""
    cur = conn.execute(
        "UPDATE suggested_tasks SET approved = 1 WHERE id = ? AND executed_at IS NULL AND approved != -1",
        (task_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def mark_executed(conn: sqlite3.Connection, task_id: int, erp_reference: str) -> None:
    """Record a successful ERP execution: set executed_at + erp_reference.
    Raises AlreadyExecutedError if executed_at is already set (prevents the
    same proposal from being pushed to ERP twice)."""
    row = get(conn, task_id)
    if row is None:
        raise ValueError(f"suggested_task {task_id} not found")
    if row["executed_at"] is not None:
        raise AlreadyExecutedError(
            f"suggested_task {task_id} already executed at {row['executed_at']}"
        )
    conn.execute(
        """
        UPDATE suggested_tasks
        SET executed_at = datetime('now'), erp_reference = ?, error_message = NULL
        WHERE id = ?
        """,
        (erp_reference, task_id),
    )
    conn.commit()


def mark_failed(conn: sqlite3.Connection, task_id: int, error_message: str) -> bool:
    """Record an ERP failure in error_message. Does NOT set executed_at, so the
    proposal can be retried later. Returns True if a row was updated."""
    cur = conn.execute(
        "UPDATE suggested_tasks SET error_message = ? WHERE id = ?",
        (error_message, task_id),
    )
    conn.commit()
    return cur.rowcount > 0
