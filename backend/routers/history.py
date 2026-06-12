from fastapi import APIRouter, Depends

from backend.database.connection import get_connection
from backend.middleware.auth import require_auth
from backend.database.repositories import decisions as decision_repo

router = APIRouter(prefix="/api/history", tags=["history"], dependencies=[Depends(require_auth)])


@router.get("")
def list_history(
    limit: int = 50,
    offset: int = 0,
    category: str | None = None,
    action: str | None = None,
    decision: str | None = None,
):
    conn = get_connection()
    try:
        filters = []
        params: list = []

        if category:
            filters.append("s.category = ?")
            params.append(category)
        if action:
            filters.append("s.suggested_action = ?")
            params.append(action)
        if decision:
            filters.append("d.decision = ?")
            params.append(decision)

        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        rows = conn.execute(
            f"""SELECT d.*, e.subject, e.from_address, e.received_at,
                       s.category, s.suggested_action, s.reasoning
                FROM decisions d
                JOIN emails e ON e.id = d.email_id
                JOIN ai_suggestions s ON s.id = d.suggestion_id
                {where}
                ORDER BY d.decided_at DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()

        total_row = conn.execute(
            f"""SELECT COUNT(*) FROM decisions d
                JOIN emails e ON e.id = d.email_id
                JOIN ai_suggestions s ON s.id = d.suggestion_id
                {where}""",
            params,
        ).fetchone()
    finally:
        conn.close()

    return {
        "total": total_row[0],
        "items": [dict(r) for r in rows],
    }
