import re
import sqlite3

REDACTION_PATTERNS: list[tuple[str, str]] = [
    # Kuwait Civil ID: 12 digits starting with 2 or 3
    (r'\b[23]\d{11}\b', '[REDACTED:CIVIL_ID]'),
    # Kuwait IBAN (KW + 2 check digits + 26 account chars = 30 total)
    (r'\bKW\d{2}[A-Z0-9]{26}\b', '[REDACTED:IBAN]'),
    # Generic IBAN (other GCC)
    (r'\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b', '[REDACTED:IBAN]'),
    # Visa/Mastercard with optional separators (space, dash, none) — 16 digits
    (r'\b(?:4\d{3}|5[1-5]\d{2})[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[REDACTED:CARD]'),
    # Amex 15-digit format (4-6-5)
    (r'\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b', '[REDACTED:CARD]'),
    # Passwords in text
    (r'(?i)(?:password|passwd|pwd)\s*[=:]\s*\S+', '[REDACTED:PASSWORD]'),
    # Anthropic API keys
    (r'\bsk-ant-[A-Za-z0-9\-_]{20,}\b', '[REDACTED:API_KEY]'),
    # Google API keys
    (r'\bAIza[A-Za-z0-9\-_]{35}\b', '[REDACTED:API_KEY]'),
]

_compiled = [(re.compile(pattern), replacement) for pattern, replacement in REDACTION_PATTERNS]


def redact(text: str) -> tuple[str, int]:
    """
    Apply all redaction patterns to text.
    Returns (redacted_text, count_of_redactions_made).
    """
    if not text:
        return text, 0

    count = 0
    result = text
    for regex, replacement in _compiled:
        new, n = regex.subn(replacement, result)
        result = new
        count += n
    return result, count


def redact_email(email: sqlite3.Row) -> tuple[str, int]:
    """
    Redact the body_text of an email row.
    Returns (redacted_body_text, redaction_count).
    Subject and headers are NOT redacted — needed for classification.
    """
    body = email["body_text"] or ""
    return redact(body)
