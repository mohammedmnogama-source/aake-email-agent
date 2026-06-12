import sqlite3

from imap_tools import A

from backend.ai.gemini_client import call_ai
from backend.ai.redactor import redact
from backend.email.fetcher import _strip_html
from backend.email.imap_client import get_mailbox

MAX_SENT_FETCH = 50
MAX_STYLE_EXAMPLES = 10
MAX_EXAMPLES_IN_PROMPT = 5

_STYLE_SYSTEM_PROMPT = """Analyze the sent emails provided and return a JSON writing style profile.
Return only valid JSON matching this exact schema — no markdown, no explanation:
{
  "greeting_style": "e.g. 'Dear [Name],' or 'Hi [Name],'",
  "signoff_style": "e.g. 'Best regards,' or 'Thanks,'",
  "sentence_length": "short|medium|long",
  "uses_bullets": true,
  "formality": "formal|semi-formal|casual",
  "bilingual": false,
  "common_phrases": ["phrase1", "phrase2"],
  "summary": "2-3 sentence description of the writing style"
}"""


def extract_style(conn: sqlite3.Connection) -> dict:
    """
    Fetch Mo's last MAX_SENT_FETCH sent emails (read-only), redact PII,
    call Claude to extract a writing style profile.

    Returns:
        {
          "profile": dict,
          "email_count": int,
          "dry_run": bool,        # True = not yet confirmed, don't save
          "examples": list[dict]  # redacted email bodies for style_examples table
        }

    Raises RuntimeError if Sent folder cannot be found.
    """
    sent_folder = _find_sent_folder(conn)

    bodies: list[str] = []
    examples: list[dict] = []

    with get_mailbox() as mb:
        mb.folder.set(sent_folder, readonly=True)

        messages = sorted(
            mb.fetch(A(all=True), mark_seen=False, bulk=True),
            key=lambda m: int(m.uid),
            reverse=True,
        )[:MAX_SENT_FETCH]

        for msg in messages:
            raw_body = msg.text or _strip_html(msg.html or "")
            if not raw_body.strip():
                continue
            redacted_body, _ = redact(raw_body)
            if not redacted_body.strip():
                continue
            bodies.append(redacted_body)
            if len(examples) < MAX_STYLE_EXAMPLES:
                examples.append({
                    "subject": msg.subject or "",
                    "body_preview": redacted_body[:200],
                    "body_full": redacted_body,
                    "context_type": "other",
                })

    if not bodies:
        raise RuntimeError(f"No usable sent emails found in '{sent_folder}'")

    user_message = "Here are Mo's sent emails to analyze:\n\n" + "\n---\n".join(bodies)

    parsed, _, _ = call_ai(
        system_prompt=_STYLE_SYSTEM_PROMPT,
        user_message=user_message,
        purpose="style_extraction",
        conn=conn,
    )

    style_confirmed = conn.execute(
        "SELECT value FROM settings WHERE key = 'style_confirmed'"
    ).fetchone()
    is_dry_run = (style_confirmed is None or style_confirmed["value"] == "0")

    return {
        "profile": parsed,
        "email_count": len(bodies),
        "dry_run": is_dry_run,
        "examples": examples,
    }


def _find_sent_folder(conn: sqlite3.Connection) -> str:
    """Return the Sent folder path, checking settings first then IMAP folder list."""
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'sent_folder'"
    ).fetchone()
    if row and row["value"]:
        return row["value"]

    # Fall back: search IMAP for a folder with "sent" in the name
    with get_mailbox() as mb:
        folders = mb.folder.list()
        for f in folders:
            name = f.name.lower()
            if "sent" in name:
                return f.name

    raise RuntimeError(
        "Could not find Sent folder. Set 'sent_folder' in settings or rename your Sent folder."
    )
