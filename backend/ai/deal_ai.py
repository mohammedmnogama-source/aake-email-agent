import json
import sqlite3

from backend.ai.gemini_client import call_ai
from backend.ai.redactor import redact
from backend.email.pdf_extractor import extract_pdf_text, pdf_to_base64
from backend.database.repositories import style as style_repo


def _build_style_block(conn: sqlite3.Connection | None) -> str:
    """Returns a style injection paragraph, or '' if no confirmed style exists."""
    if conn is None:
        return ""
    row = style_repo.get_profile(conn)
    if not row or not row["confirmed"]:
        return ""
    try:
        profile = json.loads(row["profile_json"])
    except (json.JSONDecodeError, TypeError):
        return ""
    examples = style_repo.get_examples(conn, limit=3)
    block = (
        f"\n\nWRITING STYLE — write in this exact style:\n"
        f"Greeting: {profile.get('greeting_style', '')}\n"
        f"Sign-off: {profile.get('signoff_style', '')}\n"
        f"Sentence length: {profile.get('sentence_length', '')}\n"
        f"Formality: {profile.get('formality', '')}\n"
        f"Uses bullets: {profile.get('uses_bullets', False)}\n"
        f"Style summary: {profile.get('summary', '')}\n"
    )
    for i, ex in enumerate(examples, 1):
        block += f"\n--- EXAMPLE {i} ---\n{ex['body_preview']}"
    return block


def extract_deal_from_email(email_text: str) -> dict:
    """
    Parse a pasted customer email and extract deal info.
    Returns dict: customer_name, customer_email, description, items.
    """
    redacted_text, redaction_count = redact(email_text)

    system = (
        "You are a deal extraction assistant for AAKE, an IT reseller in Kuwait "
        "(Cisco, Fortinet, HP, Microsoft). Extract deal information from the customer "
        "email below. Return JSON with exactly these keys:\n"
        "- customer_name: string (company or person name, never null)\n"
        "- customer_email: string or null\n"
        "- description: string (one short sentence summarising what they need)\n"
        "- items: array of objects, each with product_name (string), "
        "qty (integer or null), specs (string or null). List each distinct product separately.\n"
        "If a value cannot be found, use null. Never add keys that are not listed."
    )

    result, _, _ = call_ai(
        system_prompt=system,
        user_message=f"Extract deal info from this email:\n\n{redacted_text}",
        purpose="deal_extract",
        redactions_count=redaction_count,
    )
    return result


def extract_deal_from_pdf(pdf_bytes: bytes) -> dict:
    """
    Extract deal info from an uploaded PDF email file.
    If the PDF has readable text, redacts it and uses the text flow.
    If it's image-only (scanned), sends the PDF directly to Claude.
    """
    _SYSTEM = (
        "You are a deal extraction assistant for AAKE, an IT reseller in Kuwait "
        "(Cisco, Fortinet, HP, Microsoft). Extract deal information from the customer "
        "email below. Return JSON with exactly these keys:\n"
        "- customer_name: string (company or person name, never null)\n"
        "- customer_email: string or null\n"
        "- description: string (one short sentence summarising what they need)\n"
        "- items: array of objects, each with product_name (string), "
        "qty (integer or null), specs (string or null). List each distinct product separately.\n"
        "If a value cannot be found, use null. Never add keys that are not listed."
    )

    text = extract_pdf_text(pdf_bytes)

    if len(text) >= 100:
        # Text-based PDF — redact PII then extract
        return extract_deal_from_email(text)
    else:
        # Image-only (scanned) PDF — send natively to Claude
        pdf_b64 = pdf_to_base64(pdf_bytes)
        result, _, _ = call_ai(
            system_prompt=_SYSTEM,
            user_message="Extract deal info from this email PDF.",
            purpose="deal_extract_pdf",
            pdf_b64=pdf_b64,
        )
        return result


def suggest_next_step(
    deal: dict,
    items: list,
    supplier_requests: list,
    supplier_quotes: list,
    customer_quotes: list,
) -> str:
    """
    Return a plain-English sentence for what Mo should do next on this deal.
    """
    sr_sent = sum(1 for sr in supplier_requests if sr.get("status") in ("sent", "replied"))
    cq_sent = any(cq.get("status") == "sent" for cq in customer_quotes)

    context = (
        f"Deal status: {deal.get('status')}\n"
        f"Customer: {deal.get('customer_name')}\n"
        f"Line items: {len(items)}\n"
        f"Supplier requests total: {len(supplier_requests)} ({sr_sent} sent)\n"
        f"Supplier quotes received: {len(supplier_quotes)}\n"
        f"Customer quotes created: {len(customer_quotes)} (sent: {cq_sent})\n"
    )

    system = (
        "You are a deal advisor for Mo at AAKE, an IT reseller in Kuwait. "
        "Based on the deal's current stage, suggest ONE clear next action. "
        "Return JSON with one key: next_step (a single actionable plain-English sentence, max 25 words)."
    )

    result, _, _ = call_ai(
        system_prompt=system,
        user_message=context,
        purpose="deal_next_step",
    )
    return result.get("next_step", "Review the deal and determine the next step.")


def draft_supplier_request_email(
    deal: dict,
    items: list,
    vendor_name: str,
    conn: sqlite3.Connection | None = None,
) -> str:
    """
    Generate a supplier request email body Mo can copy and send.
    Returns the email body text only (no subject line).
    """
    items_text = "\n".join(
        "- " + it["product_name"]
        + (f" (Qty: {it['qty']})" if it.get("qty") else "")
        + (f" — {it['specs']}" if it.get("specs") else "")
        for it in items
    ) or "Items to be confirmed"

    context = (
        f"Supplier: {vendor_name}\n"
        f"Customer need: {deal.get('description') or 'IT equipment inquiry'}\n"
        f"Products required:\n{items_text}"
    )

    style_block = _build_style_block(conn)

    system = (
        "You are helping Mo at AAKE (IT reseller in Kuwait) write a supplier request email. "
        "Write a professional, concise email body asking the supplier for pricing and availability "
        "on the listed items. Do NOT include a subject line. Sign off as AAKE Kuwait."
        + style_block
        + "\n\nReturn JSON with one key: email_body (the full email text, ready to copy)."
    )

    result, _, _ = call_ai(
        system_prompt=system,
        user_message=context,
        purpose="deal_supplier_email",
        conn=conn,
        max_tokens=2048,
    )
    return result.get("email_body", "")


def draft_customer_quote_email(
    deal: dict,
    items: list,
    conn: sqlite3.Connection | None = None,
) -> str:
    """
    Generate a customer quote cover email body Mo can copy and send.
    Prices and totals are in the attached PDF — do NOT mention any amounts here.
    Returns the email body text only (no subject line).
    """
    items_text = "\n".join(
        "- " + it["product_name"]
        + (f" (Qty: {it['qty']})" if it.get("qty") else "")
        for it in items
    ) or "Items as discussed"

    context = (
        f"Customer: {deal.get('customer_name') or 'the customer'}\n"
        f"Inquiry: {deal.get('description') or 'IT equipment request'}\n"
        f"Items in quote:\n{items_text}"
    )

    style_block = _build_style_block(conn)

    system = (
        "You are helping Mo at AAKE (IT reseller in Kuwait) write a customer quote cover email. "
        "Write a short, professional email body to send with a quote PDF attachment. "
        "Do NOT mention any prices, amounts, or totals — those are in the attached PDF. "
        "Just introduce the quote warmly and invite the customer to reach out with questions. "
        "Do NOT include a subject line. Sign off as AAKE Kuwait."
        + style_block
        + "\n\nReturn JSON with one key: email_body (the full email text, ready to copy)."
    )

    result, _, _ = call_ai(
        system_prompt=system,
        user_message=context,
        purpose="deal_customer_quote_email",
        conn=conn,
        max_tokens=2048,
    )
    return result.get("email_body", "")
