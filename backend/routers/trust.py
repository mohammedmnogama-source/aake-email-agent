from fastapi import APIRouter, Depends, HTTPException

from backend.database.connection import get_connection
from backend.middleware.auth import require_auth
from backend.ai.trust import revoke_trust

router = APIRouter(prefix="/api/trust", tags=["trust"], dependencies=[Depends(require_auth)])


@router.get("")
def list_trust():
    """Return trust status for all categories that have been seen."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT category, streak, trusted, trusted_at, total_approved, total_edited "
            "FROM category_trust ORDER BY category"
        ).fetchall()
        threshold_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'trust_threshold'"
        ).fetchone()
        threshold = int(threshold_row["value"]) if threshold_row else 10
        return {
            "threshold": threshold,
            "categories": [dict(r) for r in rows],
        }
    finally:
        conn.close()


@router.post("/{category}/revoke")
def revoke_category_trust(category: str):
    """Mo revokes trust for a category — resets streak and trusted flag."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT category FROM category_trust WHERE category = ?", (category,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Category not found")
        revoke_trust(conn, category)
        conn.commit()
        return {"revoked": category}
    finally:
        conn.close()
