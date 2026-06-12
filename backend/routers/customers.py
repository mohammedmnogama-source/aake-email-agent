from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.database.connection import get_connection
from backend.database.repositories import customers as repo
from backend.middleware.auth import require_auth

router = APIRouter(prefix="/api/customers", tags=["customers"], dependencies=[Depends(require_auth)])


class CustomerBody(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = "Kuwait"
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    notes: Optional[str] = None


@router.get("")
def list_customers():
    conn = get_connection()
    try:
        return repo.list_customers(conn)
    finally:
        conn.close()


@router.post("")
def create_customer(body: CustomerBody):
    conn = get_connection()
    try:
        return repo.create_customer(conn, body.model_dump())
    finally:
        conn.close()


@router.get("/{customer_id}")
def get_customer(customer_id: int):
    conn = get_connection()
    try:
        c = repo.get_customer(conn, customer_id)
        if not c:
            raise HTTPException(status_code=404, detail="Customer not found")
        return c
    finally:
        conn.close()


@router.put("/{customer_id}")
def update_customer(customer_id: int, body: CustomerUpdate):
    conn = get_connection()
    try:
        c = repo.update_customer(conn, customer_id, body.model_dump(exclude_none=True))
        if not c:
            raise HTTPException(status_code=404, detail="Customer not found")
        return c
    finally:
        conn.close()


@router.delete("/{customer_id}")
def delete_customer(customer_id: int):
    conn = get_connection()
    try:
        if not repo.delete_customer(conn, customer_id):
            raise HTTPException(status_code=404, detail="Customer not found")
        return {"ok": True}
    finally:
        conn.close()
