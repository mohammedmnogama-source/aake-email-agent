from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.database.connection import get_connection
from backend.middleware.auth import require_auth

router = APIRouter(prefix="/api/facts", tags=["facts"], dependencies=[Depends(require_auth)])

VALID_CATEGORIES = {"company", "products", "delivery", "terms", "customers", "vendors", "team", "communication", "other"}


class FactBody(BaseModel):
    fact: str
    category: Optional[str] = "other"
    sort_order: Optional[int] = 0


@router.get("")
def list_facts():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, fact, category, sort_order, updated_at "
            "FROM business_facts ORDER BY category, sort_order, id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("")
def create_fact(body: FactBody):
    cat = body.category if body.category in VALID_CATEGORIES else "other"
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO business_facts (fact, category, sort_order) VALUES (?,?,?)",
            (body.fact.strip(), cat, body.sort_order or 0),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM business_facts WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.put("/{fact_id}")
def update_fact(fact_id: int, body: FactBody):
    cat = body.category if body.category in VALID_CATEGORIES else "other"
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE business_facts SET fact=?, category=?, sort_order=?, updated_at=datetime('now') WHERE id=?",
            (body.fact.strip(), cat, body.sort_order or 0, fact_id),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM business_facts WHERE id=?", (fact_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Fact not found")
        return dict(row)
    finally:
        conn.close()


@router.delete("/{fact_id}")
def delete_fact(fact_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM business_facts WHERE id=?", (fact_id,))
        conn.commit()
        return {"deleted": fact_id}
    finally:
        conn.close()
