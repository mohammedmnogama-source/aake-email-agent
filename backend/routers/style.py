import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.database.connection import get_connection
from backend.database.repositories import style as style_repo
from backend.email.style_learner import extract_style
from backend.middleware.auth import require_auth

router = APIRouter(prefix="/api/style", tags=["style"], dependencies=[Depends(require_auth)])


class ConfirmRequest(BaseModel):
    profile_json: str
    email_count: int = 0


@router.post("/refresh")
def refresh_style():
    """
    Fetch Sent emails, extract style profile.
    First time (style_confirmed=0): returns dry-run result without saving.
    After confirmed: saves profile + examples immediately.
    """
    conn = get_connection()
    try:
        result = extract_style(conn)
    except RuntimeError as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))

    if result["dry_run"]:
        conn.close()
        return {
            "dry_run": True,
            "profile": result["profile"],
            "email_count": result["email_count"],
        }

    # Already confirmed before — save the refreshed profile immediately
    style_repo.save_profile(
        conn,
        profile_json=json.dumps(result["profile"]),
        email_count=result["email_count"],
        confirmed=1,
    )
    style_repo.save_examples(conn, result["examples"])
    conn.commit()
    conn.close()
    return {"dry_run": False, "saved": True, "email_count": result["email_count"]}


@router.post("/confirm")
def confirm_style(body: ConfirmRequest):
    """Mo has reviewed the dry-run profile and confirms it. Saves to DB."""
    conn = get_connection()
    try:
        style_repo.save_profile(
            conn,
            profile_json=body.profile_json,
            email_count=body.email_count,
            confirmed=1,
        )
        style_repo.confirm_profile(conn)
        conn.commit()
    finally:
        conn.close()
    return {"confirmed": True}


@router.get("/status")
def style_status():
    """Returns current style learning status."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key IN "
            "('style_confirmed', 'style_last_updated', 'style_email_count')"
        ).fetchall()
    finally:
        conn.close()

    kv = {r["key"]: r["value"] for r in rows}
    return {
        "confirmed": kv.get("style_confirmed", "0") == "1",
        "last_updated": kv.get("style_last_updated", ""),
        "email_count": int(kv.get("style_email_count", "0")),
    }
