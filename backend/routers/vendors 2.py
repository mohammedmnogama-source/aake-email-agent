import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database.connection import get_connection
from backend.database.repositories import vendors as vendor_repo

router = APIRouter(prefix="/api/vendors", tags=["vendors"])


class VendorBody(BaseModel):
    name: str
    company: str = ""
    email: str = ""
    phone: str = ""
    brands: list[str] = []
    product_categories: list[str] = []
    notes: str = ""


@router.get("")
def list_vendors(active_only: bool = False):
    conn = get_connection()
    try:
        rows = vendor_repo.list_active(conn) if active_only else vendor_repo.list_all(conn)
    finally:
        conn.close()
    return [_format(r) for r in rows]


@router.get("/{vendor_id}")
def get_vendor(vendor_id: int):
    conn = get_connection()
    try:
        row = vendor_repo.get_by_id(conn, vendor_id)
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return _format(row)


@router.post("")
def create_vendor(body: VendorBody):
    conn = get_connection()
    try:
        vendor_id = vendor_repo.create(conn, body.model_dump())
        conn.commit()
    finally:
        conn.close()
    return {"vendor_id": vendor_id}


@router.put("/{vendor_id}")
def update_vendor(vendor_id: int, body: VendorBody):
    conn = get_connection()
    try:
        if not vendor_repo.get_by_id(conn, vendor_id):
            raise HTTPException(status_code=404, detail="Vendor not found")
        vendor_repo.update(conn, vendor_id, body.model_dump())
        conn.commit()
    finally:
        conn.close()
    return {"vendor_id": vendor_id}


@router.delete("/{vendor_id}")
def delete_vendor(vendor_id: int):
    conn = get_connection()
    try:
        if not vendor_repo.get_by_id(conn, vendor_id):
            raise HTTPException(status_code=404, detail="Vendor not found")
        vendor_repo.soft_delete(conn, vendor_id)
        conn.commit()
    finally:
        conn.close()
    return {"vendor_id": vendor_id, "deleted": True}


def _format(row) -> dict:
    d = dict(row)
    d["brands"] = json.loads(d.get("brands") or "[]")
    d["product_categories"] = json.loads(d.get("product_categories") or "[]")
    return d
