from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database.connection import get_connection
from backend.database.repositories import leads as lead_repo
from backend.middleware.auth import require_auth

router = APIRouter(prefix="/api/leads", tags=["leads"], dependencies=[Depends(require_auth)])


class LeadStatusUpdate(BaseModel):
    status: str
    notes: str | None = None


@router.get("")
def list_leads(status: str | None = None, limit: int = 100, offset: int = 0):
    conn = get_connection()
    try:
        rows = lead_repo.list_all(conn, status=status, limit=limit, offset=offset)
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.patch("/{lead_id}/status")
def update_lead_status(lead_id: int, body: LeadStatusUpdate):
    valid = {"new", "contacted", "qualified", "lost", "converted"}
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {valid}")

    conn = get_connection()
    try:
        lead_repo.update_status(conn, lead_id, body.status, body.notes)
        conn.commit()
    finally:
        conn.close()
    return {"lead_id": lead_id, "status": body.status}
