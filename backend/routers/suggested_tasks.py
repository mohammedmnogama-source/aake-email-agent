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
    conn = get_connection()
    try:
        return [dict(r) for r in repo.list_pending(conn)]
    finally:
        conn.close()


@router.get("/{task_id:int}")
def get_one(task_id: int):
    conn = get_connection()
    try:
        row = repo.get(conn, task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="suggested_task not found")
        return dict(row)
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
