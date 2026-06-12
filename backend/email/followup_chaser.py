"""
backend/email/followup_chaser.py — Phase 3.1: Follow-up chaser.

Daily job that:
1. Finds customer/lead contacts who emailed us but got no reply in N days
2. Calls Claude to write a short polite follow-up draft
3. Creates a synthetic email row (source='followup_chaser') + ai_suggestion
   so it shows up in Mo's inbox for approval like any other email

Safety rules:
- Never auto-finished (trust system explicitly skips source='followup_chaser')
- Excludes @aqeeqkw.com senders (our own emails)
- Won't create a second follow-up for the same contact within 7 days
- Skips contacts who replied after the original email
- Max 10 follow-ups per run to avoid flooding the inbox
"""

import sqlite3
from datetime import datetime, timezone

from backend.ai.gemini_client import call_ai
from backend.ai.redactor import redact


_FOLLOWUP_PROMPT = """\
You are drafting a SHORT follow-up email for Mustafa Fakhruddin (Enterprise Sales Manager, AAKE Kuwait — IT reseller).

Context:
- Contact name: {contact_name}
- Contact email: {contact_email}
- Original topic: {original_subject}
- Summary of their last message: {summary}
- Days since last contact: {days_ago}

Write a follow-up email body ONLY (no subject line). Rules:
- 2-3 sentences MAX. Do not pad or repeat yourself.
- Start with "Hi {contact_first_name}," or "Dear {contact_first_name},"
- Reference the original topic naturally.
- End with a gentle ask: are they still interested / is there an update / how would they like to proceed?
- Sign off exactly as: Mustafa Fakhruddin | Enterprise Sales Manager | AAKE
- Do NOT mention prices or amounts.
- Return ONLY the email body. No JSON. No subject line.
"""


def _get_setting(conn: sqlite3.Connection, key: str, default: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row and row["value"] else default


def find_contacts_to_chase(conn: sqlite3.Connection, threshold_days: int) -> list:
    """
    Returns one row per unique sender who:
    - Sent us a customer/lead email > threshold_days ago
    - Has NOT sent a newer email since
    - Has NOT already had a follow-up created in the last 7 days
    - Is NOT an @aqeeqkw.com address (our own emails)
    """
    rows = conn.execute(f"""
        SELECT
            e.id            AS email_id,
            e.from_address,
            e.from_name,
            e.subject,
            e.received_at,
            e.body_preview,
            s.summary,
            s.category,
            CAST((julianday('now') - julianday(e.received_at)) AS INTEGER) AS days_ago
        FROM emails e
        JOIN ai_suggestions s ON s.email_id = e.id
        WHERE s.category IN ('lead', 'customer_inquiry')
          AND e.status   = 'decided'
          AND e.source   = 'imap'
          AND LOWER(e.from_address) NOT LIKE '%@aqeeqkw.com%'
          AND e.received_at < DATETIME('now', '-{threshold_days} days')
          AND e.received_at > DATETIME('now', '-30 days')
          -- no newer email from same sender
          AND NOT EXISTS (
              SELECT 1 FROM emails newer
              WHERE LOWER(newer.from_address) = LOWER(e.from_address)
                AND newer.received_at > e.received_at
                AND newer.source = 'imap'
          )
          -- no follow-up already created for this sender in last 7 days
          AND NOT EXISTS (
              SELECT 1 FROM emails fc
              WHERE LOWER(fc.from_address) = LOWER(e.from_address)
                AND fc.source = 'followup_chaser'
                AND fc.received_at > DATETIME('now', '-7 days')
          )
        GROUP BY LOWER(e.from_address)
        ORDER BY e.received_at ASC
        LIMIT 10
    """).fetchall()
    return rows


def _generate_draft(contact: sqlite3.Row, model: str, conn: sqlite3.Connection) -> str:
    """Call Claude to write a short follow-up email body."""
    contact_name  = contact["from_name"] or contact["from_address"].split("@")[0]
    contact_first = contact_name.split()[0] if contact_name else "there"
    summary_raw   = contact["summary"] or contact["body_preview"] or "(no summary)"
    summary_clean, _ = redact(summary_raw)

    prompt = _FOLLOWUP_PROMPT.format(
        contact_name       = contact_name,
        contact_first_name = contact_first,
        contact_email      = contact["from_address"],
        original_subject   = contact["subject"] or "(no subject)",
        summary            = summary_clean[:400],
        days_ago           = contact["days_ago"],
    )

    # Simple single-turn call — no JSON, just the email body text
    try:
        result, _, _ = call_ai(
            system_prompt = "You write short professional follow-up emails. Return only the email body — no JSON, no subject line.",
            user_message  = prompt,
            model         = model,
            temperature   = 0.3,
            purpose       = "followup_chaser",
            redactions_count = 0,
            email_id      = contact["email_id"],
            conn          = conn,
            max_tokens    = 300,
            raw_text      = True,   # return plain text, not JSON
        )
        return result.strip() if isinstance(result, str) else ""
    except Exception as e:
        print(f"[chaser] Warning: Claude call failed for {contact['from_address']}: {e}")
        return ""


def _create_followup_email(conn: sqlite3.Connection, contact: sqlite3.Row, draft: str) -> int:
    """
    Insert a synthetic email row (source='followup_chaser') + ai_suggestion row.
    Returns the new email id.
    """
    now = datetime.now(timezone.utc).isoformat()
    days = contact["days_ago"]
    contact_name = contact["from_name"] or contact["from_address"]
    original_subj = contact["subject"] or "(no subject)"
    preview = f"[Follow-up needed] {days} days since last contact about: {original_subj}"

    # Synthetic email row
    cur = conn.execute(
        """
        INSERT INTO emails
            (subject, from_name, from_address, to_addresses,
             body_text, body_preview, received_at, fetched_at,
             source, status, is_read)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'followup_chaser', 'decided', 0)
        """,
        (
            f"Follow-up: {original_subj}",
            f"⏰ {contact_name}",
            contact["from_address"],
            "mustafa@aqeeqkw.com",
            f"[FOLLOW-UP REMINDER]\n\n{preview}\n\nSuggested draft:\n\n{draft}",
            preview,
            now,
            now,
        )
    )
    email_id = cur.lastrowid

    # Pre-built ai_suggestion row (no Claude analysis needed — we already have the draft)
    conn.execute(
        """
        INSERT INTO ai_suggestions
            (email_id, model_used, category, suggested_action,
             reasoning, summary, draft_subject, draft_to,
             draft_content, needs_clarification, manually_handled, auto_finished)
        VALUES (?, 'followup_chaser', 'customer_inquiry', 'draft_reply',
                ?, ?, ?, ?,
                ?, 0, 0, 0)
        """,
        (
            email_id,
            f"Follow-up: {contact_name} hasn't replied in {days} days.",
            f"No reply from {contact_name} in {days} days (re: {original_subj}).",
            f"Re: {original_subj}",
            contact["from_address"],
            draft,
        )
    )
    return email_id


def run_followup_chaser(conn: sqlite3.Connection) -> int:
    """
    Main entry point — called by the daily scheduler job.
    Returns the number of follow-up suggestions created.
    """
    enabled = _get_setting(conn, "followup_enabled", "1")
    if enabled != "1":
        return 0

    threshold = int(_get_setting(conn, "followup_threshold_days", "4"))

    # Get AI model
    model_row = conn.execute("SELECT value FROM settings WHERE key = 'ai_model'").fetchone()
    model = model_row["value"] if model_row else "claude-haiku-4-5-20251001"

    contacts = find_contacts_to_chase(conn, threshold)
    if not contacts:
        print("[chaser] No contacts to follow up with today.")
        return 0

    created = 0
    for contact in contacts:
        try:
            draft = _generate_draft(contact, model, conn)
            if not draft:
                continue
            _create_followup_email(conn, contact, draft)
            conn.commit()
            created += 1
            print(f"[chaser] Created follow-up for {contact['from_address']} ({contact['days_ago']}d silence)")
        except Exception as e:
            print(f"[chaser] Error processing {contact['from_address']}: {e}")

    return created
