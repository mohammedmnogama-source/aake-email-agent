import json
import sqlite3

import anthropic

from backend.config import settings
from backend.database.repositories import audit


def call_ai(
    system_prompt: str,
    user_message: str,
    model: str = "claude-haiku-4-5-20251001",
    temperature: float = 0.2,
    purpose: str = "email_analysis",
    redactions_count: int = 0,
    email_id: int | None = None,
    conn: sqlite3.Connection | None = None,
    pdf_b64: str | None = None,
    max_tokens: int = 1024,
    raw_text: bool = False,  # if True, return plain text instead of parsed JSON
) -> tuple[dict | str, int, int]:
    """
    Call Claude with structured JSON output.
    Returns (parsed_dict, input_tokens, output_tokens).
    Logs every call to api_audit_log if conn is provided.
    If pdf_b64 is provided, the PDF is sent as a native document block (for image-only PDFs).
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Build message content — plain text or PDF document block
    if pdf_b64:
        content = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": pdf_b64,
                },
            },
            {"type": "text", "text": user_message},
        ]
    else:
        content = user_message

    system_suffix = "" if raw_text else "\n\nIMPORTANT: Return only valid JSON. No markdown, no code fences."

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt + system_suffix,
        messages=[{"role": "user", "content": content}],
    )

    response_text = response.content[0].text.strip()

    if raw_text:
        parsed = response_text
    else:
        # Strip markdown fences if Claude adds them despite instructions
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()
        parsed = json.loads(response_text)

    if conn is not None:
        audit.log_call(
            conn=conn,
            model=model,
            purpose=purpose,
            prompt=system_prompt + user_message,
            response=response_text,
            redactions_count=redactions_count,
            email_id=email_id,
        )

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    return parsed, input_tokens, output_tokens
