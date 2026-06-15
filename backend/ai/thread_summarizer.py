"""
backend/ai/thread_summarizer.py

Builds a whole-thread briefing for an email — CONTEXT / SUMMARY / STATUS / NEXT STEPS.

The thread is found by base subject (Re:/Fwd: stripped), falling back to the same
sender when the subject match is thin. PII is redacted from each body before it is
sent to Claude.

Used in two places (one shared code path):
  1. At sync time — analyzer.py calls build_thread_summary() for every new email
     and stores the result in ai_suggestions.thread_summary.
  2. On demand — the POST /api/inbox/{id}/thread-summary endpoint.
"""

import re

from backend.ai.gemini_client import call_ai
from backend.ai.redactor import redact


def strip_re_fwd(subject: str) -> str:
    """Strip Re:/Fwd: prefixes so replies group with their original by subject."""
    s = (subject or "").strip()
    while True:
        stripped = re.sub(r'^(Re|RE|Fwd|FW|Fw|AW|回复):\s*', '', s).strip()
        if stripped == s:
            break
        s = stripped
    return s.lower()


def build_thread_summary(conn, email_id: int) -> tuple[int, str] | None:
    """
    Return (thread_count, summary_text) for the thread this email belongs to,
    or None if the email does not exist. summary_text is plain text in the
    CONTEXT / SUMMARY / STATUS / NEXT STEPS format.
    """
    email = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    if not email:
        return None

    base_subj = strip_re_fwd(email["subject"] or "")

    # All emails from the last 90 days — the pool we group a thread out of.
    all_rows = conn.execute(
        "SELECT id, subject, from_name, from_address, to_addresses, received_at, "
        "body_text, body_preview "
        "FROM emails WHERE datetime(received_at) >= datetime('now', '-90 days') "
        "ORDER BY received_at ASC"
    ).fetchall()

    # Match by base subject; if that gives only this one email, fall back to
    # everything from the same sender.
    thread = [r for r in all_rows if strip_re_fwd(r["subject"] or "") == base_subj]
    if len(thread) <= 1:
        sender = (email["from_address"] or "").lower()
        thread = [r for r in all_rows if (r["from_address"] or "").lower() == sender]

    # Build the thread text Claude reads, redacting PII from each body.
    parts = []
    for i, e in enumerate(thread, 1):
        body_raw = e["body_text"] or e["body_preview"] or "(empty)"
        body_clean, _ = redact(body_raw)
        parts.append(
            f"--- EMAIL {i} of {len(thread)} ---\n"
            f"Date:    {e['received_at'] or 'unknown'}\n"
            f"From:    {e['from_name'] or e['from_address'] or 'Unknown'}\n"
            f"To:      {e['to_addresses'] or '—'}\n"
            f"Subject: {e['subject'] or '(no subject)'}\n\n"
            f"{body_clean[:2000]}"
        )
    thread_text = "\n\n".join(parts)

    # Business facts give Claude the company context.
    facts_rows = conn.execute(
        "SELECT fact FROM business_facts ORDER BY category, id"
    ).fetchall()
    facts_block = "\n".join(r["fact"] for r in facts_rows) if facts_rows else ""

    model_row = conn.execute(
        "SELECT value FROM settings WHERE key = 'ai_model'"
    ).fetchone()
    model = model_row["value"] if model_row else "claude-haiku-4-5-20251001"

    system_prompt = (
        "You are an executive assistant for Mo (Mustafa Fakhruddin, Enterprise Sales Manager) "
        "at AAKE Kuwait — an IT reseller dealing in Cisco, Fortinet, HP, Dell, Microsoft, etc.\n\n"
        f"Business context:\n{facts_block}\n\n"
        "Analyze the email thread below and give Mo a clear, concise briefing. "
        "Be direct, professional, and business-focused."
    )

    user_message = (
        f"Here is an email thread ({len(thread)} email(s)), oldest to newest:\n\n"
        f"{thread_text}\n\n"
        "Respond in this exact format — no extra text:\n\n"
        "CONTEXT\n"
        "[Who are the parties? What is this thread about? 2–3 sentences.]\n\n"
        "SUMMARY\n"
        "[What has been discussed, sent, requested, or agreed so far? 3–5 sentences.]\n\n"
        "STATUS\n"
        "[Where does this stand right now? What is waiting or unresolved? 1–2 sentences.]\n\n"
        "NEXT STEPS\n"
        "- [Most important action]\n"
        "- [Second action if needed]\n"
        "- [Third action if needed]"
    )

    result, _, _ = call_ai(
        system_prompt=system_prompt,
        user_message=user_message,
        model=model,
        max_tokens=700,
        purpose="thread_summary",
        raw_text=True,
    )

    return len(thread), result
