"""
Inbox endpoints.

POST /api/inbox/sync          — start background sync (fetch + analyze)
GET  /api/inbox/sync-status   — poll this for live progress during sync
POST /api/inbox/backfill      — one-time: read all sent emails + index everything to ChromaDB
GET  /api/inbox               — list all emails and their AI suggestions
GET  /api/inbox/{id}          — full detail for one email (with AI suggestion)
POST /api/inbox/{id}/approve  — save the AI draft to IMAP Drafts folder
POST /api/inbox/{id}/reject   — mark email as rejected (no draft needed)
"""

import threading
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from backend.middleware.auth import require_auth
from pydantic import BaseModel
from backend import sync_tracker


class ApproveRequest(BaseModel):
    draft_content: Optional[str] = None


class ErpRfqRequest(BaseModel):
    subject:       str
    description:   Optional[str] = None
    notes:         Optional[str] = None
    received_date: Optional[str] = None
    customer_name: Optional[str] = None


class ErpLeadRequest(BaseModel):
    first_name:  str
    last_name:   Optional[str] = None
    company:     Optional[str] = None
    email:       Optional[str] = None
    phone:       Optional[str] = None
    notes:       Optional[str] = None


class ErpTaskRequest(BaseModel):
    title:       str
    description: Optional[str] = None
    priority:    Optional[str] = "medium"
    due_date:    Optional[str] = None

class ComposeRequest(BaseModel):
    description: str            # what Mo wants to say, in plain words
    to_name:     Optional[str] = None
    to_email:    Optional[str] = None
    subject:     Optional[str] = None

class RedraftRequest(BaseModel):
    current_draft: str          # Mo's edited version or notes
    instruction:   Optional[str] = None  # e.g. "make it shorter", "mention Friday"

router = APIRouter(prefix="/api/inbox", tags=["inbox"], dependencies=[Depends(require_auth)])


@router.post("/sync")
def sync_inbox():
    """
    Start a background sync: fetch new emails from IMAP then analyze them.
    Returns immediately. Poll GET /sync-status for live progress.
    """
    status = sync_tracker.get()
    if status["running"]:
        return {"started": False, "message": "Sync already in progress."}

    def _run():
        from backend.email.fetcher import fetch_new_emails
        from backend.ai.analyzer import analyze_pending
        try:
            sync_tracker.start()
            new_ids = fetch_new_emails()
            analyzed_ids = analyze_pending()
            sync_tracker.finish(len(new_ids), len(analyzed_ids))
        except Exception as e:
            sync_tracker.fail(str(e))

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "message": "Sync started — poll /api/inbox/sync-status for progress."}


@router.get("/sync-status")
def get_sync_status():
    """Live sync progress — poll this every second while syncing."""
    return sync_tracker.get()


@router.post("/compose")
def compose_email(body: ComposeRequest):
    """
    Draft an email from scratch based on what Mo wants to say.
    Mo types a plain description, Claude writes the full short email.
    """
    from backend.ai.gemini_client import call_ai
    from backend.database.connection import get_connection
    from backend.rag.approved_store import query_approved_examples

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'ai_model'"
        ).fetchone()
        model = row["value"] if row else "claude-haiku-4-5-20251001"
    finally:
        conn.close()

    # Pull similar approved drafts so Claude matches Mo's style
    examples = []
    try:
        examples = query_approved_examples(
            subject=body.subject or "",
            body_preview=body.description,
            n=3,
        )
    except Exception:
        pass

    # Build the prompt
    recipient = body.to_name or body.to_email or "the recipient"
    lines = [
        f"Draft a short professional email to {recipient}.",
        f"What Mo wants to say: {body.description}",
    ]
    if body.subject:
        lines.append(f"Subject context: {body.subject}")

    if examples:
        lines.append(
            "\nHere are real emails Mo previously approved — match this tone and length exactly:"
        )
        for i, ex in enumerate(examples, 1):
            lines.append(f"\n--- Example {i} ---\n{ex['approved_content']}")

    system = (
        "You are a professional email assistant for Mohammed at AAKE Kuwait, an IT reseller. "
        "Write a short email based on Mo's instruction. "
        "STRICT RULES: 3-5 sentences maximum. No fluff. Direct and professional. "
        "Greet once, state the point, close. Return ONLY the email body text — no subject line, "
        "no labels, no explanation. Just the email body starting from the greeting."
    )

    result, _, _ = call_ai(
        system_prompt=system,
        user_message="\n".join(lines),
        model=model,
        temperature=0.3,
        purpose="compose",
        redactions_count=0,
        email_id=None,
        conn=None,
        max_tokens=512,
        raw_text=True,  # return plain text, not JSON
    )

    return {
        "draft": result,
        "subject": body.subject or "",
        "to_email": body.to_email or "",
        "to_name": body.to_name or "",
    }


@router.post("/backfill")
def backfill():
    """
    One-time job: index existing inbox emails into ChromaDB.
    Safe to run multiple times — already-indexed emails are skipped.
    """
    from backend.rag.store import backfill_existing_emails, backfill_inbox_history
    from backend.database.connection import get_connection

    conn = get_connection()
    try:
        inbox_count = backfill_existing_emails(conn)
        history_count = backfill_inbox_history(conn, limit=200)
    finally:
        conn.close()

    return {
        "inbox_emails_indexed": inbox_count,
        "inbox_history_indexed": history_count,
        "message": f"Indexed {inbox_count} DB emails + {history_count} inbox history into ChromaDB",
    }


@router.post("/run-followup-chaser")
def run_followup_chaser_now():
    """
    Manually trigger the follow-up chaser right now (normally runs daily at 8 AM).
    Returns the number of new follow-up suggestions created.
    """
    from backend.email.followup_chaser import run_followup_chaser
    from backend.database.connection import get_connection
    conn = get_connection()
    try:
        n = run_followup_chaser(conn)
        return {"created": n, "message": f"{n} follow-up suggestion(s) added to inbox"}
    finally:
        conn.close()


@router.post("/sent-sync")
def start_sent_sync():
    """
    Start indexing the full Sent folder into the sent_history ChromaDB collection.
    Runs in a background thread — returns immediately.
    Poll GET /api/inbox/sent-sync/status for live progress.
    """
    from backend.rag.sent_store import backfill_sent_history, get_sync_status
    from backend.database.connection import get_connection

    status = get_sync_status()
    if status["running"]:
        return {"started": False, "message": "Sent sync already running."}

    def _run():
        conn = get_connection()
        try:
            backfill_sent_history(conn)
        finally:
            conn.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"started": True, "message": "Sent history sync started."}


@router.get("/sent-sync/status")
def get_sent_sync_status():
    """
    Live progress for the sent-sync job.
    Returns: running, indexed, total, done, error, collection_count.
    """
    from backend.rag.sent_store import get_sync_status
    return get_sync_status()


@router.get("/learning-stats")
def learning_stats():
    """
    Phase 1.5: learning progress for the inbox widget.
    Returns approval counts, per-category edit rates, and sent_history size.
    """
    from backend.database.connection import get_connection
    from backend.rag.sent_store import get_count as sent_count

    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) as n FROM approved_drafts").fetchone()["n"]
        unedited = conn.execute(
            "SELECT COUNT(*) as n FROM approved_drafts WHERE was_edited = 0"
        ).fetchone()["n"]

        cat_rows = conn.execute(
            """
            SELECT email_category,
                   COUNT(*) as total,
                   SUM(CASE WHEN was_edited = 0 THEN 1 ELSE 0 END) as unedited
            FROM approved_drafts
            WHERE email_category IS NOT NULL
            GROUP BY email_category
            """
        ).fetchall()

        by_category = {
            r["email_category"]: {
                "total": r["total"],
                "unedited": r["unedited"],
                "pct_clean": round(r["unedited"] / r["total"] * 100) if r["total"] else 0,
            }
            for r in cat_rows
        }

        return {
            "approved_total": total,
            "approved_unedited": unedited,
            "pct_clean_overall": round(unedited / total * 100) if total else 0,
            "by_category": by_category,
            "sent_history_count": sent_count(),
        }
    finally:
        conn.close()


@router.get("")
def list_emails(status: str = None, limit: int = 50, ids: str = None):
    """
    List all emails in the database.

    Optional filter: ?status=pending  or  ?status=decided  etc.
    Optional filter: ?ids=12,45,67  → returns exactly those emails (used by the
    daily briefing, where each point links to the emails it refers to).

    Each item includes the AI suggestion if one exists.
    """
    from backend.database.connection import get_connection

    # Same columns used by every branch below
    cols = (
        "SELECT e.id, e.subject, e.from_address, e.from_name, e.body_preview, "
        "e.received_at, e.fetched_at, e.status, e.source, e.is_read, "
        "s.category, s.suggested_action, s.summary, s.thread_summary, s.draft_content, s.auto_finished, "
        "s.manually_handled, "
        "(SELECT COUNT(*) FROM approved_drafts WHERE email_id = e.id) as was_approved "
        "FROM emails e "
        "LEFT JOIN ai_suggestions s ON s.email_id = e.id "
    )

    conn = get_connection()
    try:
        if ids:
            id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
            if not id_list:
                return []
            placeholders = ",".join("?" * len(id_list))
            rows = conn.execute(
                cols + f"WHERE e.id IN ({placeholders}) ORDER BY e.id DESC",
                id_list,
            ).fetchall()
        elif status:
            rows = conn.execute(
                "SELECT e.id, e.subject, e.from_address, e.from_name, e.body_preview, "
                "e.received_at, e.fetched_at, e.status, e.source, e.is_read, "
                "s.category, s.suggested_action, s.summary, s.thread_summary, s.draft_content, s.auto_finished, "
                "s.manually_handled, "
                "(SELECT COUNT(*) FROM approved_drafts WHERE email_id = e.id) as was_approved "
                "FROM emails e "
                "LEFT JOIN ai_suggestions s ON s.email_id = e.id "
                "WHERE e.status = ? "
                "ORDER BY e.id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT e.id, e.subject, e.from_address, e.from_name, e.body_preview, "
                "e.received_at, e.fetched_at, e.status, e.source, e.is_read, "
                "s.category, s.suggested_action, s.summary, s.thread_summary, s.draft_content, s.auto_finished, "
                "s.manually_handled, "
                "(SELECT COUNT(*) FROM approved_drafts WHERE email_id = e.id) as was_approved "
                "FROM emails e "
                "LEFT JOIN ai_suggestions s ON s.email_id = e.id "
                "ORDER BY e.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows]


@router.get("/{email_id:int}")
def get_email(email_id: int):
    """
    Full detail for one email: the email itself + the AI suggestion + draft reply.
    """
    from backend.database.connection import get_connection

    conn = get_connection()
    try:
        email = conn.execute(
            "SELECT * FROM emails WHERE id = ?", (email_id,)
        ).fetchone()
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")

        suggestion = conn.execute(
            "SELECT * FROM ai_suggestions WHERE email_id = ?", (email_id,)
        ).fetchone()
    finally:
        conn.close()

    return {
        "email": dict(email),
        "suggestion": dict(suggestion) if suggestion else None,
    }


_ERP_BASE  = "https://frontend-gamma-seven-9d9hr1vyhv.vercel.app"
_ERP_URL   = f"{_ERP_BASE}/api/rfqs"
_LEADS_URL = f"{_ERP_BASE}/api/leads"
_TASKS_URL = f"{_ERP_BASE}/api/tasks"


def _erp_post(url: str, payload: dict):
    """Helper — POST to ERP from server side (no CORS issues)."""
    import httpx
    payload = {k: v for k, v in payload.items() if v}
    try:
        r = httpx.post(url, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"ERP error {e.response.status_code}: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach ERP: {str(e)}")


@router.post("/{email_id}/send-to-erp")
def send_to_erp(email_id: int, body: ErpRfqRequest):
    """
    Creates an RFQ in the Aqeeq Intelligence ERP from an email.
    Called by the frontend — we proxy to the ERP from the server side
    so there are no CORS issues.
    """
    import httpx
    payload = {
        "subject":       body.subject,
        "description":   body.description or "",
        "notes":         body.notes or "",
        "received_date": body.received_date or "",
        "customer_name": body.customer_name or "",
    }
    # Remove empty optional fields so ERP uses its defaults
    payload = {k: v for k, v in payload.items() if v}

    return _erp_post(_ERP_URL, payload)


@router.post("/{email_id}/save-as-lead")
def save_as_lead(email_id: int, body: ErpLeadRequest):
    """Save the email sender as a Lead in Aqeeq Intelligence ERP."""
    return _erp_post(_LEADS_URL, {
        "first_name":  body.first_name,
        "last_name":   body.last_name,
        "company":     body.company,
        "email":       body.email,
        "phone":       body.phone,
        "notes":       body.notes,
        "lead_source": "email_agent",
    })


@router.post("/{email_id}/create-task")
def create_erp_task(email_id: int, body: ErpTaskRequest):
    """Create a follow-up Task in Aqeeq Intelligence ERP."""
    return _erp_post(_TASKS_URL, {
        "title":       body.title,
        "description": body.description,
        "priority":    body.priority,
        "due_date":    body.due_date,
    })


@router.patch("/{email_id}/read")
def mark_read(email_id: int):
    """Mark an email as read."""
    from backend.database.connection import get_connection
    conn = get_connection()
    try:
        conn.execute("UPDATE emails SET is_read = 1 WHERE id = ?", (email_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/{email_id}/approve")
def approve_draft(email_id: int, body: ApproveRequest = ApproveRequest()):
    """
    Save the AI draft reply to the IMAP Drafts folder.
    In test_mode: writes to data/test_drafts/ instead of real IMAP.
    Returns the draft UID if saved to IMAP, or the file path in test mode.
    """
    from backend.database.connection import get_connection
    from backend.email.draft_saver import save_draft

    conn = get_connection()
    try:
        email = conn.execute(
            "SELECT * FROM emails WHERE id = ?", (email_id,)
        ).fetchone()
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")

        suggestion = conn.execute(
            "SELECT * FROM ai_suggestions WHERE email_id = ?", (email_id,)
        ).fetchone()
        if not suggestion:
            raise HTTPException(status_code=404, detail="No AI suggestion for this email")
        # Use the edited draft from the request body if provided, else fall back to DB
        final_draft = (body.draft_content or "").strip() or suggestion["draft_content"]
        if not final_draft:
            raise HTTPException(status_code=400, detail="This email has no draft reply to approve")

        # Check test mode
        test_mode = conn.execute(
            "SELECT value FROM settings WHERE key = 'test_mode'"
        ).fetchone()
        is_test = test_mode and test_mode["value"] == "1"

        to_addr = suggestion["draft_to"] or email["from_address"] or ""
        subject = suggestion["draft_subject"] or f"Re: {email['subject'] or '(no subject)'}"
        body = final_draft

        if is_test:
            # Write to test_drafts folder instead of real IMAP
            import os
            from datetime import datetime, timezone
            os.makedirs("data/test_drafts", exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = f"data/test_drafts/{ts}_{email_id}_draft.txt"
            with open(path, "w") as f:
                f.write(f"To: {to_addr}\nSubject: {subject}\n\n{body}")
            conn.execute(
                "UPDATE ai_suggestions SET manually_handled = 1 WHERE email_id = ?",
                (email_id,)
            )
            conn.commit()
            # Learn from this approval
            _save_approved_draft(conn, email_id, email, suggestion, final_draft)
            return {"saved": True, "test_mode": True, "path": path}

        # Real mode: save to IMAP Drafts
        uid = save_draft(to=to_addr, subject=subject, body=body)
        conn.execute(
            "UPDATE ai_suggestions SET manually_handled = 1 WHERE email_id = ?",
            (email_id,)
        )
        conn.commit()
        # Learn from this approval
        _save_approved_draft(conn, email_id, email, suggestion, final_draft)
        return {"saved": True, "test_mode": False, "draft_uid": uid}

    finally:
        conn.close()


def _save_approved_draft(conn, email_id: int, email, suggestion, final_draft: str):
    """
    Save an approved draft to the approved_drafts table + ChromaDB.
    Called after every approval (test mode or real mode).
    Detects whether Mo edited the draft before approving.
    """
    original = (suggestion["draft_content"] or "").strip()
    was_edited = 1 if final_draft.strip() != original else 0

    # Save to SQLite
    conn.execute(
        """
        INSERT INTO approved_drafts
            (email_id, email_subject, email_from_name, email_from_address,
             email_category, original_draft, approved_content, was_edited)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            email_id,
            email["subject"] or "",
            email["from_name"] or "",
            email["from_address"] or "",
            suggestion["category"] or "",
            original,
            final_draft,
            was_edited,
        ),
    )
    conn.commit()
    draft_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Index to ChromaDB so future emails can learn from this
    try:
        from backend.rag import approved_store
        approved_store.index_approved_draft(
            draft_id=draft_id,
            subject=email["subject"] or "",
            from_name=email["from_name"] or "",
            category=suggestion["category"] or "",
            approved_content=final_draft,
            was_edited=was_edited,
        )
        edited_note = " (Mo edited it)" if was_edited else ""
        print(f"[learn] Saved approved draft {draft_id} for email {email_id}{edited_note}")
    except Exception as e:
        print(f"[learn] Warning: could not index approved draft to ChromaDB: {e}")

    # Update trust streak for this category
    try:
        from backend.ai.trust import update_trust_streak
        update_trust_streak(conn, suggestion["category"] or "", was_edited)
        conn.commit()
    except Exception as e:
        print(f"[learn] Warning: could not update trust streak: {e}")


@router.post("/{email_id}/redraft")
def redraft(email_id: int, body: RedraftRequest):
    """
    Re-generate the draft using Mo's edits or instructions as guidance.
    Mo can edit the draft, add a note like "make it shorter", and hit Re-draft.
    Returns a new draft string.
    """
    from backend.ai.gemini_client import call_ai
    from backend.database.connection import get_connection
    from backend.ai.redactor import redact

    conn = get_connection()
    try:
        email = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")

        suggestion = conn.execute(
            "SELECT * FROM ai_suggestions WHERE email_id = ?", (email_id,)
        ).fetchone()

        model_row = conn.execute("SELECT value FROM settings WHERE key = 'ai_model'").fetchone()
        model = model_row["value"] if model_row else "claude-haiku-4-5-20251001"
    finally:
        conn.close()

    # Redact the email body before sending to Claude
    clean_body, _ = redact(email["body_text"] or email["body_preview"] or "")
    clean_subject, _ = redact(email["subject"] or "")
    sender = email["from_name"] or email["from_address"] or ""

    # Build the re-draft prompt
    lines = [
        f"Rewrite the reply to this email.",
        f"",
        f"ORIGINAL EMAIL:",
        f"From: {sender}",
        f"Subject: {clean_subject}",
        f"",
        clean_body[:800],
    ]

    if body.current_draft.strip():
        lines += [
            f"",
            f"MO'S CURRENT VERSION (keep his key points and intent):",
            body.current_draft.strip(),
        ]

    if body.instruction and body.instruction.strip():
        lines += [
            f"",
            f"MO'S INSTRUCTION: {body.instruction.strip()}",
        ]

    system = (
        "You are a professional email assistant for Mohammed at AAKE Kuwait, an IT reseller. "
        "Rewrite the email reply based on Mo's version and any instruction he gave. "
        "STRICT RULES: 3-5 sentences maximum. Short and direct. No fluff. Professional. "
        "Keep Mo's key points and intent. Return ONLY the email body — no subject line, "
        "no explanation, no labels. Start from the greeting."
    )

    new_draft, _, _ = call_ai(
        system_prompt=system,
        user_message="\n".join(lines),
        model=model,
        temperature=0.3,
        purpose="redraft",
        redactions_count=0,
        email_id=email_id,
        conn=None,
        max_tokens=512,
        raw_text=True,
    )

    return {"draft": new_draft}


@router.post("/{email_id}/reject")
def reject_draft(email_id: int):
    """
    Mark the AI suggestion as rejected — no draft needed for this email.
    """
    from backend.database.connection import get_connection

    conn = get_connection()
    try:
        suggestion = conn.execute(
            "SELECT id FROM ai_suggestions WHERE email_id = ?", (email_id,)
        ).fetchone()
        if not suggestion:
            raise HTTPException(status_code=404, detail="No AI suggestion for this email")
        conn.execute(
            "UPDATE ai_suggestions SET manually_handled = 1 WHERE email_id = ?",
            (email_id,)
        )
        conn.commit()
    finally:
        conn.close()
    return {"rejected": True}


@router.get("/daily-summary")
def get_daily_summary(_: str = Depends(require_auth)):
    """Return the last cached daily briefing, or null if none exists."""
    import json as _json
    from backend.database.connection import get_connection
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM daily_briefing WHERE id = 1").fetchone()
        if not row:
            return None
        return {
            "email_count":  row["email_count"],
            "generated_at": row["generated_at"],
            "overview":     row["overview"],
            "attention":    _json.loads(row["attention_json"]),
            "vendors":      _json.loads(row["vendors_json"]),
            "priorities":   _json.loads(row["priorities_json"]),
        }
    finally:
        conn.close()


@router.post("/daily-summary")
def daily_summary(_: str = Depends(require_auth)):
    """
    Summarize all emails from the last 48 hours (today + yesterday).
    Returns a plain-text daily briefing with highlights and next steps.
    """
    from backend.database.connection import get_connection
    from backend.ai.gemini_client import call_ai
    from backend.ai.redactor import redact

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT e.id, e.subject, e.from_name, e.from_address, e.received_at, "
            "e.body_text, e.body_preview, e.source, "
            "s.category, s.summary, s.suggested_action, s.manually_handled, "
            "(SELECT COUNT(*) FROM approved_drafts WHERE email_id = e.id) as was_approved "
            "FROM emails e "
            "LEFT JOIN ai_suggestions s ON s.email_id = e.id "
            "WHERE datetime(e.received_at) >= datetime('now', '-2 days') "
            "AND e.source != 'followup_chaser' "
            "ORDER BY e.received_at DESC LIMIT 60"
        ).fetchall()

        if not rows:
            return {"email_count": 0, "summary_text": "No emails in the last 48 hours."}

        facts_rows = conn.execute("SELECT fact FROM business_facts ORDER BY category, id").fetchall()
        facts_block = "\n".join(r["fact"] for r in facts_rows) if facts_rows else ""

        model_row = conn.execute("SELECT value FROM settings WHERE key = 'ai_model'").fetchone()
        model = model_row["value"] if model_row else "claude-haiku-4-5-20251001"

        # Build a compact one-line-per-email list (keep input tokens small)
        lines = []
        for e in rows:
            status = "accepted" if e["was_approved"] else ("dismissed" if e["manually_handled"] else "pending")
            ai_note = (e["summary"] or "")[:80]  # cap at 80 chars
            # Prefix with #id so Claude can tag each briefing item with the emails it refers to
            line = (
                f"#{e['id']} [{e['category'] or 'other'}] {(e['subject'] or '(no subject)')[:60]} "
                f"| {e['from_name'] or e['from_address'] or 'Unknown'} | {status}"
            )
            if ai_note:
                line += f" | {ai_note}"
            lines.append(line)

        emails_block = "\n".join(lines)

        system_prompt = (
            "You are an executive assistant briefing Mo (Mustafa Fakhruddin, Enterprise Sales Manager) "
            "at AAKE Kuwait — IT reseller (Cisco, Fortinet, HP, Dell, Microsoft, etc.).\n\n"
            f"Business context:\n{facts_block}\n\n"
            "Return ONLY valid JSON. No markdown, no asterisks, no code fences. Plain text values only."
        )

        user_message = (
            f"Emails from the last 48 hours ({len(rows)} total):\n\n"
            f"{emails_block}\n\n"
            "Return ONLY this JSON — keep each string value SHORT (under 120 chars):\n"
            '{"overview":"...","attention":[{"title":"...","contact":"...","detail":"...","email_ids":[1,2]}],'
            '"vendors":[{"title":"...","contact":"...","detail":"...","email_ids":[3]}],"priorities":["...","...","..."]}\n\n'
            "Rules: attention = pending emails needing action only. vendors = vendor replies/quotes only. "
            "Every attention and vendor item MUST include email_ids — the list of #numbers (integers only) "
            "of the emails from the list above that the item refers to. "
            "priorities = max 3 actions. Skip spam/internal/dismissed/accepted. No markdown."
        )

        result, _, _ = call_ai(
            system_prompt=system_prompt,
            user_message=user_message,
            model=model,
            max_tokens=1400,
            purpose="daily_summary",
            raw_text=False,
        )

        import json as _json
        from datetime import datetime, timezone
        overview   = result.get("overview", "")
        attention  = result.get("attention", [])
        vendors    = result.get("vendors", [])
        priorities = result.get("priorities", [])

        # Persist to DB so it survives server restarts
        conn.execute(
            "INSERT INTO daily_briefing (id, generated_at, email_count, overview, attention_json, vendors_json, priorities_json) "
            "VALUES (1, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "generated_at=excluded.generated_at, email_count=excluded.email_count, "
            "overview=excluded.overview, attention_json=excluded.attention_json, "
            "vendors_json=excluded.vendors_json, priorities_json=excluded.priorities_json",
            (
                datetime.now(timezone.utc).isoformat(),
                len(rows),
                overview,
                _json.dumps(attention),
                _json.dumps(vendors),
                _json.dumps(priorities),
            )
        )
        conn.commit()

        return {
            "email_count": len(rows),
            "overview":    overview,
            "attention":   attention,
            "vendors":     vendors,
            "priorities":  priorities,
        }

    finally:
        conn.close()


@router.post("/{email_id}/thread-summary")
def summarize_thread(email_id: int, _: str = Depends(require_auth)):
    """
    Summarize the full email thread related to this email — on demand.
    New emails get this automatically at sync time (stored in ai_suggestions.thread_summary);
    this endpoint is the fallback for older emails synced before that feature.
    Uses the same shared builder, then persists the result so it shows next time too.
    """
    from backend.database.connection import get_connection
    from backend.ai.thread_summarizer import build_thread_summary

    conn = get_connection()
    try:
        result = build_thread_summary(conn, email_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Email not found")
        thread_count, summary_text = result

        # Persist it so the ERP shows it automatically next time (and only pays once).
        conn.execute(
            "UPDATE ai_suggestions SET thread_summary = ? WHERE email_id = ?",
            (summary_text, email_id),
        )
        conn.commit()

        return {
            "thread_count": thread_count,
            "summary_text": summary_text,
        }

    finally:
        conn.close()
