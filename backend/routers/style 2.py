import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.ai.gemini_client import call_ai
from backend.ai.redactor import redact
from backend.database.connection import get_connection
from backend.database.repositories import style as style_repo
from backend.email.style_learner import _STYLE_SYSTEM_PROMPT, extract_style

router = APIRouter(prefix="/api/style", tags=["style"])


class ConfirmRequest(BaseModel):
    profile_json: str
    email_count: int = 0


class PasteStyleRequest(BaseModel):
    emails: list[str]  # 2–5 raw email body strings Mo pastes directly


@router.post("/paste")
def paste_style(body: PasteStyleRequest):
    """
    Mo pastes 2–5 emails he wrote. Extracts his writing style profile.
    Returns the profile for Mo to review. Call POST /api/style/confirm to activate.
    """
    if len(body.emails) < 2 or len(body.emails) > 5:
        raise HTTPException(status_code=422, detail="Paste between 2 and 5 emails.")

    conn = get_connection()
    try:
        # Redact PII from each pasted email before sending to Claude
        redacted_bodies = []
        examples = []
        for raw in body.emails:
            redacted, _ = redact(raw)
            if redacted.strip():
                redacted_bodies.append(redacted)
                examples.append({
                    "subject": None,
                    "body_preview": redacted[:200],
                    "body_full": redacted,
                    "context_type": "pasted",
                })

        if not redacted_bodies:
            raise HTTPException(status_code=422, detail="No email body content after redaction.")

        joined = "\n\n---\n\n".join(redacted_bodies)
        user_message = f"Here are emails I have written:\n\n{joined}"

        parsed, _, _ = call_ai(
            system_prompt=_STYLE_SYSTEM_PROMPT,
            user_message=user_message,
            purpose="style_extract_paste",
            conn=conn,
        )

        style_repo.save_profile(
            conn,
            profile_json=json.dumps(parsed),
            email_count=len(redacted_bodies),
            confirmed=0,
        )
        style_repo.save_examples(conn, examples)
        conn.commit()
    finally:
        conn.close()

    return {"profile": parsed, "email_count": len(redacted_bodies)}


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
