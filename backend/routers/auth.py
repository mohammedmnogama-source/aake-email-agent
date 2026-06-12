import bcrypt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.database.connection import get_connection
from backend.middleware.auth import create_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginRequest):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'dashboard_password'"
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=500, detail="Password not set. Run setup.py first.")

    stored_hash = row["value"].encode()
    if not bcrypt.checkpw(body.password.encode(), stored_hash):
        raise HTTPException(status_code=401, detail="Invalid password")

    return {"token": create_token()}
