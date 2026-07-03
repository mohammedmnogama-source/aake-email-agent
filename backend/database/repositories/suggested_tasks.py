"""Repository for the `suggested_tasks` staging table.

IMPORTANT: this is a STAGING / SCRATCHPAD layer only. ERP/Supabase remains the
real CRM and system of record. Nothing here calls ERP or writes CRM records —
it only stores *proposed* actions for human review, and records the result of an
ERP call that the execute route performs after approval.

Approval state (unchanged):
    approved =  0  -> pending review   (the default)
    approved =  1  -> approved, NOT yet executed   (does NOT call ERP)
    approved = -1  -> rejected / dismissed

Execution state machine (migration 021 columns):
    execution_status ∈ {pending, executing, executed, failed}
    execution_claimed_at   UTC time the current claim was taken (NULL when idle)
    execution_attempt_id   opaque fence for the worker holding the claim
    executed_at            set ONLY together with a valid erp_reference (terminal)
    erp_reference          ERP task UUID once reconciled
    agent_suggestion_key   permanent opaque idempotency identity (UUIDv4)

Only the execute route drives executing/executed/failed. Approval never calls
ERP; editing an approved-but-unexecuted row resets it to pending approval.
"""

import json
import sqlite3
import uuid

# How long a row may sit in `executing` before another human click may reclaim
# it (crash / lost worker recovery). Kept in one place so SQL and callers agree.
STALE_CLAIM_SECONDS = 120


class AlreadyExecutedError(Exception):
    """Raised when trying to execute a proposal whose executed_at is already set."""


class NotEditableError(Exception):
    """Raised when an edit is attempted on an executing/executed row."""


# Fields a human is allowed to edit via update(). Deliberately excludes approval
# and all execution-state columns — those are state, not user-editable content.
_EDITABLE_FIELDS = {"task_type", "description", "payload", "confidence", "evidence_quote"}


def _new_key() -> str:
    return str(uuid.uuid4())


def create(conn: sqlite3.Connection, data: dict) -> int:
    """Insert a new staged proposal. Returns its id.

    Required keys: email_id, suggestion_id, task_type, description.
    Optional: payload (dict -> stored as JSON, or str), confidence (float),
    evidence_quote (str), sequence_order (int).

    Every new row is given a permanent opaque agent_suggestion_key (UUIDv4) that
    is reused for ERP idempotency on every future execution attempt.
    """
    payload = data.get("payload")
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)

    cursor = conn.execute(
        """
        INSERT INTO suggested_tasks (
            email_id, suggestion_id, sequence_order, task_type, description,
            payload, confidence, evidence_quote, agent_suggestion_key,
            execution_status
        ) VALUES (
            :email_id, :suggestion_id, :sequence_order, :task_type, :description,
            :payload, :confidence, :evidence_quote, :agent_suggestion_key,
            'pending'
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
            "agent_suggestion_key": _new_key(),
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


def list_approved(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Approved proposals (approved = 1) in any execution state, newest first.
    Includes a computed `execution_is_stale` flag so the UI can decide whether an
    `executing` row may be re-triggered."""
    return conn.execute(
        """
        SELECT st.*,
               CASE
                 WHEN st.execution_status = 'executing'
                      AND st.execution_claimed_at IS NOT NULL
                      AND st.execution_claimed_at < datetime('now', ?)
                 THEN 1 ELSE 0
               END AS execution_is_stale,
               e.subject      AS email_subject,
               e.from_address AS email_from,
               e.from_name    AS email_from_name,
               e.received_at  AS email_received_at
        FROM suggested_tasks st
        LEFT JOIN emails e ON e.id = st.email_id
        WHERE st.approved = 1
        ORDER BY st.created_at DESC
        """,
        (f"-{STALE_CLAIM_SECONDS} seconds",),
    ).fetchall()


def get(conn: sqlite3.Connection, task_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM suggested_tasks WHERE id = ?", (task_id,)
    ).fetchone()


def is_stale_claim(row: sqlite3.Row, conn: sqlite3.Connection) -> bool:
    """True if `row` is `executing` but its claim is older than the stale
    threshold (so a human may reclaim it). Uses the DB clock for consistency."""
    if row["execution_status"] != "executing" or row["execution_claimed_at"] is None:
        return False
    r = conn.execute(
        "SELECT (? < datetime('now', ?)) AS stale",
        (row["execution_claimed_at"], f"-{STALE_CLAIM_SECONDS} seconds"),
    ).fetchone()
    return bool(r["stale"])


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
    """Edit human-editable content. Rejects edits on executing/executed rows
    (raises NotEditableError). A successful content edit on a non-executed row
    also RESETS it to pending approval and clears any prior execution state, so
    a stale approval can never be executed against edited content.

    Returns True if a row was updated, False if nothing editable was supplied or
    the row does not exist.
    """
    row = get(conn, task_id)
    if row is None:
        return False
    if row["executed_at"] is not None or row["execution_status"] in ("executing", "executed"):
        raise NotEditableError(
            f"suggested_task {task_id} is {row['execution_status']} and cannot be edited"
        )

    payload = fields.get("payload")
    if isinstance(payload, (dict, list)):
        fields = {**fields, "payload": json.dumps(payload)}

    clean = {k: v for k, v in fields.items() if k in _EDITABLE_FIELDS}
    if not clean:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in clean)
    # Editing invalidates any prior approval / failed execution state.
    set_clause += (
        ", approved = 0, execution_status = 'pending', "
        "execution_claimed_at = NULL, execution_attempt_id = NULL, error_message = NULL"
    )
    values = list(clean.values()) + [task_id]
    cur = conn.execute(
        f"UPDATE suggested_tasks SET {set_clause} WHERE id = ?", values
    )
    conn.commit()
    return cur.rowcount > 0


def reject(conn: sqlite3.Connection, task_id: int) -> bool:
    """Soft-reject / dismiss a proposal (approved = -1). Keeps the row for audit.
    Never touches executing/executed rows, and never creates an ERP task."""
    cur = conn.execute(
        """
        UPDATE suggested_tasks SET approved = -1
        WHERE id = ? AND executed_at IS NULL
          AND execution_status NOT IN ('executing', 'executed')
        """,
        (task_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def set_approved(conn: sqlite3.Connection, task_id: int) -> bool:
    """Mark a proposal approved (approved = 1). This ONLY flips the flag — it
    does NOT call ERP, never sets executed_at/erp_reference, and preserves the
    stable agent_suggestion_key. Won't touch rejected, executing or executed
    rows."""
    cur = conn.execute(
        """
        UPDATE suggested_tasks SET approved = 1
        WHERE id = ? AND executed_at IS NULL AND approved != -1
          AND execution_status NOT IN ('executing', 'executed')
        """,
        (task_id,),
    )
    conn.commit()
    return cur.rowcount > 0


def claim_execution(
    conn: sqlite3.Connection, task_id: int
) -> tuple[sqlite3.Row, str] | None:
    """Atomically claim an approved create_task row for execution.

    Succeeds (returns (fresh_row, attempt_id)) only when the single guarded
    UPDATE changes exactly one row, i.e. the row is create_task, approved, not
    executed, has a non-blank key, and is either pending/failed or an
    `executing` claim older than STALE_CLAIM_SECONDS. Otherwise returns None
    (already executing fresh, already executed, ineligible, or lost the race).
    """
    attempt_id = str(uuid.uuid4())
    cur = conn.execute(
        """
        UPDATE suggested_tasks
        SET execution_status = 'executing',
            execution_claimed_at = datetime('now'),
            execution_attempt_id = ?,
            error_message = NULL
        WHERE id = ?
          AND task_type = 'create_task'
          AND approved = 1
          AND executed_at IS NULL
          AND agent_suggestion_key IS NOT NULL
          AND TRIM(agent_suggestion_key) != ''
          AND (
                execution_status IN ('pending', 'failed')
                OR (execution_status = 'executing'
                    AND execution_claimed_at IS NOT NULL
                    AND execution_claimed_at < datetime('now', ?))
              )
        """,
        (attempt_id, task_id, f"-{STALE_CLAIM_SECONDS} seconds"),
    )
    conn.commit()
    if cur.rowcount != 1:
        return None
    return get(conn, task_id), attempt_id


def reconcile_executed(
    conn: sqlite3.Connection, task_id: int, attempt_id: str, erp_reference: str
) -> bool:
    """Record a successful ERP execution, fenced by attempt_id.

    executed_at and erp_reference are written together in ONE update, and only
    for the worker that still holds the claim (attempt_id match). A stale/older
    worker whose attempt was reclaimed cannot overwrite the result. Returns True
    if this attempt won the fence.
    """
    if not erp_reference or not str(erp_reference).strip():
        raise ValueError("refusing to mark executed without a valid erp_reference")
    cur = conn.execute(
        """
        UPDATE suggested_tasks
        SET execution_status = 'executed',
            executed_at = datetime('now'),
            erp_reference = ?,
            execution_claimed_at = NULL,
            execution_attempt_id = NULL,
            error_message = NULL
        WHERE id = ?
          AND execution_status = 'executing'
          AND execution_attempt_id = ?
          AND executed_at IS NULL
        """,
        (erp_reference, task_id, attempt_id),
    )
    conn.commit()
    return cur.rowcount > 0


def mark_failed(
    conn: sqlite3.Connection, task_id: int, attempt_id: str, error_message: str
) -> bool:
    """Record a safe ERP failure, fenced by attempt_id. Keeps executed_at and
    erp_reference NULL so the row stays retryable (no automatic retry). A
    stale/older worker cannot clobber a newer reclaimed attempt. Returns True if
    this attempt won the fence."""
    cur = conn.execute(
        """
        UPDATE suggested_tasks
        SET execution_status = 'failed',
            execution_claimed_at = NULL,
            execution_attempt_id = NULL,
            error_message = ?
        WHERE id = ?
          AND execution_status = 'executing'
          AND execution_attempt_id = ?
          AND executed_at IS NULL
        """,
        (error_message, task_id, attempt_id),
    )
    conn.commit()
    return cur.rowcount > 0


def mark_executed(conn: sqlite3.Connection, task_id: int, erp_reference: str) -> None:
    """Legacy direct helper (kept for existing tests). Sets executed_at +
    erp_reference + execution_status='executed' in one update. Raises
    AlreadyExecutedError if executed_at is already set. The execute route uses
    claim_execution/reconcile_executed instead of this."""
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
        SET executed_at = datetime('now'), erp_reference = ?,
            execution_status = 'executed', error_message = NULL
        WHERE id = ?
        """,
        (erp_reference, task_id),
    )
    conn.commit()
