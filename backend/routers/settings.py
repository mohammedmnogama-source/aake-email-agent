import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database.connection import get_connection
from backend.middleware.auth import require_auth

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_auth)])

_EDITABLE_KEYS = {
    "poll_interval_min", "test_mode", "use_style_for_drafts", "ai_model",
}


class SettingUpdate(BaseModel):
    value: str


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.get("")
def get_settings():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT key, value, description FROM settings").fetchall()
    finally:
        conn.close()
    # Never expose the hashed password
    return {
        r["key"]: {"value": r["value"], "description": r["description"] or ""}
        for r in rows
        if r["key"] != "dashboard_password"
    }


@router.patch("/{key}")
def update_setting(key: str, body: SettingUpdate):
    if key not in _EDITABLE_KEYS:
        raise HTTPException(status_code=403, detail=f"Key '{key}' is not editable via API")

    conn = get_connection()
    try:
        conn.execute("UPDATE settings SET value = ? WHERE key = ?", (body.value, key))
        conn.commit()
    finally:
        conn.close()
    return {"key": key, "value": body.value}


@router.post("/change-password")
def change_password(body: PasswordChange):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'dashboard_password'"
        ).fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="No password set")

        stored = row["value"].encode()
        if not bcrypt.checkpw(body.current_password.encode(), stored):
            raise HTTPException(status_code=401, detail="Current password is wrong")

        new_hash = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt()).decode()
        conn.execute(
            "UPDATE settings SET value = ? WHERE key = 'dashboard_password'", (new_hash,)
        )
        conn.commit()
    finally:
        conn.close()
    return {"changed": True}


@router.get("/audit-log")
def get_audit_log(limit: int = 50):
    conn = get_connection()
    try:
        from backend.database.repositories import audit
        rows = audit.list_recent(conn, limit=limit)
    finally:
        conn.close()
    return [dict(r) for r in rows]
