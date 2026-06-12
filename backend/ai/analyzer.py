"""
backend/ai/analyzer.py — The brain of the email agent (Phase 2).

What this file does, step by step:
  1. Reads emails from the DB that have status='pending'
  2. Removes personal info (Civil IDs, IBANs, etc.) from the email body
  3. Asks ChromaDB: "find me 3 similar past emails we handled before"
  4. Builds a prompt for Claude with: the new email + those 3 similar ones + Mo's writing style
  5. Calls Claude → gets back: email category, suggested action, and a draft reply
  6. Saves that result into the ai_suggestions table
  7. Saves this email to ChromaDB so it can help future queries
  8. Marks the email as 'decided' in the DB

Run manually:
    python -m backend.ai.analyzer

Called automatically by scheduler.py after every email fetch.
"""

import json
import sqlite3

from backend.ai.gemini_client import call_ai
from backend.ai.redactor import redact
from backend.ai.deal_ai import _build_style_block
from backend.ai.models import GeminiResponse, EmailCategory, SuggestedAction
from backend.database.connection import get_connection
from backend.database.repositories import suggestions as suggestion_repo
from backend.rag import store as rag_store
from backend.rag import approved_store
from backend import sync_tracker


# The system prompt that tells Claude what it is and what format to return.
# Mo is at AAKE Kuwait — IT reseller for Cisco, Fortinet, HP, Microsoft.
_SYSTEM_PROMPT = """\
You are an email assistant for AAKE Kuwait, an IT reseller specialising in \
Cisco, Fortinet, HP, and Microsoft products.

HOW AAKE WORKS (important context):
- Mo is the sales person. He deals directly with CUSTOMERS only.
- AAKE has a separate purchasing account (purchase@aqeeqkw.com) that handles all \
supplier/vendor interactions on Mo's behalf.
- Whenever the purchasing account communicates with a supplier, they CC Mo so he \
stays informed. These are informational emails — Mo NEVER replies to suppliers directly.
- So: emails from purchase@aqeeqkw.com OR from known supplier domains (Redington, \
Maimoon, Ingram, Logicom, Mindware, Exclusive Networks, etc.) are supplier-related \
and Mo only needs a summary + any key pricing/quote info extracted.

Your job for each email:
1. Classify the email into a category
2. Decide the best action to take
3. Only write a draft reply for CUSTOMER emails (leads, customer inquiries)

Categories (pick one):
- lead               — new potential customer asking about products
- vendor_quote_request — supplier/vendor quote or pricing info (CC'd to Mo)
- customer_inquiry   — existing customer with a question or order follow-up
- internal           — internal team message (from purchase@aqeeqkw.com or AAKE staff)
- spam               — junk or irrelevant
- other              — does not fit above

Actions (pick one):
- draft_reply        — write a reply (ONLY for customer emails: leads, customer_inquiry)
- extract_lead_info  — extract contact details and save as a lead
- summarize_only     — summarise the email and extract key info (use for ALL supplier/vendor emails)
- create_rfq         — create a Request For Quotation in the system
- no_action          — nothing to do

IMPORTANT RULES:
- Return ONLY valid JSON. No markdown. No explanation outside the JSON.
- If writing a draft reply, write it in the language the sender used (Arabic or English).
- draft_content must be the full email body — not a subject line.
- Never mention prices, amounts, or totals in a draft unless they were in the original email.
- For vendor_quote_request or internal category: always use summarize_only, never draft_reply.
- For emails from purchase@aqeeqkw.com: category=internal, action=summarize_only.

DRAFT STYLE — Mo's writing style (follow strictly):
- SHORT. 3-5 sentences max. No padding, no fluff.
- Get straight to the point — acknowledge, state next step, close.
- No long explanations. No bullet lists in replies unless absolutely necessary.
- Greet once, close once. Nothing extra.
- Professional but direct. Like a busy person who respects the reader's time.

Return JSON matching exactly this structure:
{
  "category": "<one of the categories above>",
  "suggested_action": "<one of the actions above>",
  "reasoning": "<1-2 sentences: why you chose this action>",
  "summary": "<2-3 sentence plain summary of this email>",
  "draft_subject": "<reply subject line, or null>",
  "draft_to": "<reply-to email address, or null>",
  "draft_content": "<full draft reply body, or null>",
  "needs_clarification": false,
  "confidence_note": "<optional: if you are unsure about something>"
}"""


def analyze_pending() -> list[int]:
    """
    Process all emails with status='pending'.
    Returns list of email IDs that were successfully analyzed.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, subject, from_address, from_name, body_text, to_addresses "
            "FROM emails "
            "WHERE status = 'pending' AND source = 'imap' "
            "ORDER BY id"
        ).fetchall()

        if not rows:
            return []

        model = _get_model_setting(conn)
        processed = []
        total = len(rows)

        for i, row in enumerate(rows, 1):
            email_id = row["id"]
            subject = row["subject"] or "(no subject)"
            sync_tracker.set_analyzing(i, total, subject)
            try:
                _mark_status(conn, email_id, "processing")
                conn.commit()

                _analyze_one(conn, row, model)
                processed.append(email_id)

            except Exception as e:
                print(f"[analyzer] Error on email {email_id}: {e}")
                _mark_status(conn, email_id, "error")
                conn.commit()

        return processed

    finally:
        conn.close()


def _analyze_one(conn: sqlite3.Connection, row: sqlite3.Row, model: str) -> None:
    """
    Full pipeline for a single email row.
    """
    email_id = row["id"]
    body_text = row["body_text"] or ""
    subject = row["subject"] or ""
    from_address = row["from_address"] or ""

    # Step 1: Check if this sender domain is in the "skip" list
    if _is_manually_handled(conn, from_address):
        _mark_status(conn, email_id, "skipped")
        conn.commit()
        print(f"[analyzer] Email {email_id} skipped (manually handled pattern)")
        return

    # Step 2: Redact PII from the email body before sending to Claude
    clean_body, redaction_count = redact(body_text)
    clean_subject, _ = redact(subject)

    # Step 3a: Get top-2 similar past emails from ChromaDB (incoming email RAG)
    rag_context = _build_rag_context(clean_body, clean_subject)

    # Step 3b: Get top-3 approved draft examples — what Mo actually wrote for similar emails
    approved_examples = _build_approved_context(clean_body, clean_subject)

    # Step 3c (1.4): Get top-2 similar sent emails — Mo's own voice
    sent_examples = _build_sent_context(clean_body, clean_subject)

    # Step 3d (1.3): Look up sender in customers + deals tables
    sender_context = _build_sender_context(conn, from_address)

    # Step 4: Get Mo's writing style (injected into the draft reply)
    tone_type = _detect_tone_type(conn, from_address)
    style_block = _build_style_block(conn)

    # Step 5: Build the full prompt for Claude
    user_message = _build_user_message(
        subject=clean_subject,
        from_address=from_address,
        from_name=row["from_name"] or "",
        body=clean_body,
        rag_context=rag_context,
        approved_examples=approved_examples,
        sent_examples=sent_examples,
        sender_context=sender_context,
    )

    facts_block = _load_facts_block(conn)
    full_system = _SYSTEM_PROMPT + facts_block + style_block

    # Step 6: Call Claude
    result_dict, input_tokens, output_tokens = call_ai(
        system_prompt=full_system,
        user_message=user_message,
        model=model,
        temperature=0.2,
        purpose="email_analysis",
        redactions_count=redaction_count,
        email_id=email_id,
        conn=conn,
        max_tokens=2048,
    )

    # Step 7: Validate Claude's response (make sure the values are ones we know)
    category = _safe_category(result_dict.get("category"))
    suggested_action = _safe_action(result_dict.get("suggested_action"))

    # Step 8: Save the suggestion to the database
    suggestion_repo.create(conn, {
        "email_id": email_id,
        "model_used": model,
        "category": category,
        "suggested_action": suggested_action,
        "reasoning": result_dict.get("reasoning", ""),
        "summary": result_dict.get("summary"),
        "draft_subject": result_dict.get("draft_subject"),
        "draft_to": result_dict.get("draft_to") or from_address,
        "draft_content": result_dict.get("draft_content"),
        "extracted_data": json.dumps(result_dict.get("extracted_data")) if result_dict.get("extracted_data") else None,
        "suggested_vendor_id": result_dict.get("suggested_vendor_id"),
        "confidence_note": result_dict.get("confidence_note"),
        "raw_response": json.dumps(result_dict),
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "few_shot_count": len(rag_context),
        "needs_clarification": 1 if result_dict.get("needs_clarification") else 0,
        "clarification_type": result_dict.get("clarification_type"),
        "clarification_question": result_dict.get("clarification_question"),
        "clarification_options": json.dumps(result_dict.get("clarification_options")) if result_dict.get("clarification_options") else None,
        "suggested_recipients": None,
        "clarification_round": 0,
        "manually_handled": 0,
    })

    # Step 8.5: Auto-finish if category is trusted (Phase 2)
    _maybe_auto_finish(conn, email_id, category, result_dict)

    # Step 9: Index this email to ChromaDB for future RAG queries
    try:
        rag_store.index_email(
            email_id=email_id,
            body_text=body_text,  # store.py will redact internally
            subject=subject,
            from_address=from_address,
            tone_type=tone_type,
            action_taken=suggested_action,
        )
        conn.execute(
            "UPDATE emails SET rag_indexed = 1 WHERE id = ?", (email_id,)
        )
    except Exception as e:
        # ChromaDB failure should not block the analysis from being saved
        print(f"[analyzer] Warning: failed to index email {email_id} to ChromaDB: {e}")

    # Step 10: Mark email as decided
    _mark_status(conn, email_id, "decided")
    conn.commit()
    print(f"[analyzer] Email {email_id} analyzed — action: {suggested_action}")


def _build_rag_context(body_text: str, subject: str) -> list[dict]:
    """
    Queries ChromaDB for the 3 most similar past emails.
    Returns [] if ChromaDB is empty (first run) — graceful fallback.
    """
    try:
        return rag_store.query_similar(body_text=body_text, subject=subject, n=3)
    except Exception as e:
        print(f"[analyzer] Warning: RAG query failed: {e}")
        return []


def _build_user_message(
    subject: str,
    from_address: str,
    from_name: str,
    body: str,
    rag_context: list[dict],
    approved_examples: list[dict] = None,
    sent_examples: list[dict] = None,
    sender_context: str = "",
) -> str:
    sender = from_name or from_address

    lines = [
        "=== NEW EMAIL ===",
        f"From: {sender} <{from_address}>",
        f"Subject: {subject}",
        "",
        body,
    ]

    # Section 1.3: what we know about this sender (deals, customer history)
    if sender_context:
        lines.append(f"\n{sender_context}")

    # Section 1.4 priority 1: approved draft examples (strongest style signal)
    if approved_examples:
        lines.append(
            "\n=== APPROVED REPLY EXAMPLES ==="
            "\nThese are real replies Mo approved. Match this tone and style exactly."
        )
        for i, ex in enumerate(approved_examples, 1):
            edited_note = " [Mo edited before approving]" if ex.get("was_edited") else ""
            lines.append(f"\n--- Approved Example {i}{edited_note} ---")
            lines.append(f"Subject context: {ex['subject']}")
            lines.append(ex["approved_content"])

    # Section 1.4 priority 2: sent email examples (Mo's own voice)
    if sent_examples:
        lines.append(
            "\n=== HOW MO WRITES (from his Sent folder) ==="
            "\nUse these as secondary style references when drafting."
        )
        for i, ex in enumerate(sent_examples, 1):
            lines.append(f"\n--- Sent Example {i} ---")
            lines.append(f"Subject: {ex['subject']}")
            preview = ex["document"][:300] + ("..." if len(ex["document"]) > 300 else "")
            lines.append(preview)

    # Section 1.4 priority 3: similar past incoming emails (classification context)
    if rag_context:
        lines.append("\n=== SIMILAR PAST EMAILS (how these were handled) ===")
        for i, past in enumerate(rag_context, 1):
            lines.append(f"\n--- Past Email {i} ---")
            lines.append(f"Subject: {past['subject']}")
            preview = past["document"][:250] + ("..." if len(past["document"]) > 250 else "")
            lines.append(preview)
            if past["action_taken"]:
                lines.append(f"How it was handled: {past['action_taken']}")

    return "\n".join(lines)


def _build_approved_context(body_text: str, subject: str) -> list[dict]:
    """
    Queries the approved_drafts ChromaDB collection for similar past approved replies.
    Returns [] if no approvals yet — graceful fallback for first run.
    """
    try:
        return approved_store.query_approved_examples(
            subject=subject,
            body_preview=body_text[:500],  # first 500 chars is enough for similarity
            n=3,
        )
    except Exception as e:
        print(f"[analyzer] Warning: approved examples query failed: {e}")
        return []


def _build_sent_context(body_text: str, subject: str) -> list[dict]:
    """
    Phase 1.4: query the sent_history ChromaDB collection for similar emails Mo sent.
    Returns [] gracefully if collection is empty.
    """
    try:
        from backend.rag.sent_store import query_sent_similar
        query = f"Subject: {subject}\n\n{body_text}"
        return query_sent_similar(query, n=2)
    except Exception as e:
        print(f"[analyzer] Warning: sent history query failed: {e}")
        return []


def _build_sender_context(conn: sqlite3.Connection, from_address: str) -> str:
    """
    Phase 1.3: look up the sender in customers + deals tables.
    Returns a formatted block describing what AAKE knows about this sender,
    or an empty string if nothing is found.
    """
    if not from_address or "@" not in from_address:
        return ""

    domain = from_address.split("@")[-1].lower()
    lines = []

    # Look up customer by exact email or domain match
    customer = conn.execute(
        "SELECT id, name, company FROM customers "
        "WHERE LOWER(email) = ? OR LOWER(email) LIKE ?",
        (from_address.lower(), f"%@{domain}"),
    ).fetchone()

    if customer:
        label = customer["company"] or customer["name"]
        lines.append(f"Known customer: {customer['name']}" + (f" ({label})" if customer["company"] else ""))
        cust_id = customer["id"]
    else:
        cust_id = None

    # Find open deals for this sender (by email or customer_id)
    deal_rows = conn.execute(
        """
        SELECT ref_number, status, description, created_at,
               CAST((julianday('now') - julianday(created_at)) AS INTEGER) AS age_days
        FROM deals
        WHERE status NOT IN ('won','fulfilled','closed','lost','cancelled')
          AND (LOWER(customer_email) = ? OR (? IS NOT NULL AND customer_id = ?))
        ORDER BY created_at DESC
        LIMIT 5
        """,
        (from_address.lower(), cust_id, cust_id),
    ).fetchall()

    if deal_rows:
        lines.append(f"Open deals ({len(deal_rows)}):")
        for d in deal_rows:
            desc = (d["description"] or "")[:60]
            lines.append(f"  • {d['ref_number']} [{d['status']}] — {desc} ({d['age_days']}d old)")

    # Last email received from this sender
    last_email = conn.execute(
        "SELECT received_at FROM emails WHERE LOWER(from_address) = ? "
        "AND received_at IS NOT NULL ORDER BY received_at DESC LIMIT 1",
        (from_address.lower(),),
    ).fetchone()

    if last_email and last_email["received_at"]:
        last = conn.execute(
            "SELECT CAST((julianday('now') - julianday(?)) AS INTEGER) AS days",
            (last_email["received_at"],),
        ).fetchone()
        if last and last["days"] is not None:
            lines.append(f"Last email from them: {last['days']} day(s) ago")

    if not lines:
        return ""

    return "=== WHAT WE KNOW ABOUT THIS SENDER ===\n" + "\n".join(lines)


def _detect_tone_type(conn: sqlite3.Connection, from_address: str) -> str:
    """
    Returns 'supplier' if the sender is a known vendor, 'customer' otherwise.
    Used to pick the right writing style when drafting a reply.
    """
    if not from_address or "@" not in from_address:
        return "customer"

    domain = from_address.split("@")[-1].lower()

    row = conn.execute(
        "SELECT id FROM vendors WHERE LOWER(email) LIKE ? OR LOWER(email) LIKE ?",
        (f"%@{domain}", f"%{domain}%"),
    ).fetchone()

    return "supplier" if row else "customer"


def _is_manually_handled(conn: sqlite3.Connection, from_address: str) -> bool:
    """
    Returns True if the sender's domain is in the manually_handled_patterns table.
    These emails are skipped — Mo handles them himself.
    """
    if not from_address or "@" not in from_address:
        return False
    domain = from_address.split("@")[-1].lower()
    row = conn.execute(
        "SELECT id FROM manually_handled_patterns WHERE LOWER(from_domain) = ?",
        (domain,),
    ).fetchone()
    return row is not None


def _safe_category(value: str | None) -> str:
    """Returns value if it's a valid EmailCategory, otherwise 'other'."""
    valid = {e.value for e in EmailCategory}
    return value if value in valid else "other"


def _safe_action(value: str | None) -> str:
    """Returns value if it's a valid SuggestedAction, otherwise 'no_action'."""
    valid = {e.value for e in SuggestedAction}
    return value if value in valid else "no_action"


def _mark_status(conn: sqlite3.Connection, email_id: int, status: str) -> None:
    conn.execute("UPDATE emails SET status = ? WHERE id = ?", (status, email_id))


def _load_facts_block(conn: sqlite3.Connection) -> str:
    """
    Loads all business facts from the DB and returns them as a prompt block.
    Returns empty string if no facts exist yet.
    """
    try:
        rows = conn.execute(
            "SELECT fact FROM business_facts ORDER BY category, sort_order, id"
        ).fetchall()
    except Exception:
        return ""  # table may not exist on very old installs — degrade gracefully

    if not rows:
        return ""

    facts_text = "\n".join(f"- {r['fact']}" for r in rows)
    return f"\n\nCOMPANY FACTS (use these when drafting replies):\n{facts_text}\n"


def _get_model_setting(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'ai_model'"
    ).fetchone()
    return row["value"] if row else "claude-haiku-4-5-20251001"


def _maybe_auto_finish(
    conn: sqlite3.Connection,
    email_id: int,
    category: str,
    result_dict: dict,
) -> None:
    """
    Phase 2: if the category is trusted and all safety checks pass,
    auto-finish this email by writing the draft to IMAP Drafts (or test file).
    Records the action in actions_taken and marks auto_finished=1.
    """
    from backend.ai.trust import is_category_trusted, draft_has_prices

    draft = (result_dict.get("draft_content") or "").strip()

    # Must have a draft and not need clarification
    if not draft or result_dict.get("needs_clarification"):
        return

    # Category must be trusted
    if not is_category_trusted(conn, category):
        return

    # Safety: never auto-finish if draft mentions prices
    if draft_has_prices(draft):
        print(f"[trust] Email {email_id}: auto-finish blocked (prices in draft)")
        return

    # Get the suggestion row we just inserted
    suggestion = conn.execute(
        "SELECT * FROM ai_suggestions WHERE email_id = ?", (email_id,)
    ).fetchone()
    email_row = conn.execute(
        "SELECT * FROM emails WHERE id = ?", (email_id,)
    ).fetchone()
    if not suggestion or not email_row:
        return

    to_addr = suggestion["draft_to"] or email_row["from_address"] or ""
    subject = suggestion["draft_subject"] or f"Re: {email_row['subject'] or '(no subject)'}"

    # Check test mode
    test_mode_row = conn.execute(
        "SELECT value FROM settings WHERE key = 'test_mode'"
    ).fetchone()
    is_test = test_mode_row and test_mode_row["value"] == "1"

    try:
        if is_test:
            import os
            from datetime import datetime, timezone
            os.makedirs("data/test_drafts", exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = f"data/test_drafts/{ts}_{email_id}_auto.txt"
            with open(path, "w") as f:
                f.write(f"[AUTO-FINISHED]\nTo: {to_addr}\nSubject: {subject}\n\n{draft}")
            dest = path
        else:
            from backend.email.draft_saver import save_draft
            dest = str(save_draft(to=to_addr, subject=subject, body=draft))

        # Mark suggestion as auto-finished
        conn.execute(
            "UPDATE ai_suggestions SET auto_finished = 1, manually_handled = 1 WHERE email_id = ?",
            (email_id,)
        )
        # Record in actions_taken
        conn.execute(
            """INSERT INTO actions_taken (email_id, action_type, details, created_at)
               VALUES (?, 'auto_finish', ?, datetime('now'))""",
            (email_id, f"Auto-finished [{category}] → {dest}")
        )
        conn.commit()
        print(f"[trust] Email {email_id} auto-finished (category={category}, test={is_test})")

    except Exception as e:
        print(f"[trust] Warning: auto-finish failed for email {email_id}: {e}")


# Allow running this file directly for manual testing:
#   python -m backend.ai.analyzer
if __name__ == "__main__":
    from backend.config import settings
    from backend.database.connection import init_db
    init_db(settings.database_path)
    ids = analyze_pending()
    print(f"Analyzed {len(ids)} email(s): {ids}")
