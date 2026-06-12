import imaplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend.config import settings
from backend.database.connection import get_connection


def save_draft(to: str, subject: str, body: str) -> int | None:
    """
    Append a draft message to the IMAP Drafts folder with the \\Draft flag.
    Returns the server-assigned UID of the saved draft, or None if the server
    doesn't return an APPENDUID response (still succeeds — draft is saved).
    """
    drafts_folder = _get_drafts_folder()
    mime = _build_mime(to, subject, body)
    raw_bytes = mime.as_bytes()

    ctx = ssl.create_default_context()
    with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port, ssl_context=ctx) as imap:
        imap.login(settings.email_address, settings.email_password)

        # SELECT the drafts folder so APPEND lands in the right place
        status, _ = imap.select(f'"{drafts_folder}"')
        if status != "OK":
            # Some servers use unquoted names
            imap.select(drafts_folder)

        now = imaplib.Time2Internaldate(datetime.now(timezone.utc).timetuple())
        typ, data = imap.append(
            f'"{drafts_folder}"',
            r"(\Draft)",
            now,
            raw_bytes,
        )

        if typ != "OK":
            raise RuntimeError(f"IMAP APPEND failed: {data}")

        # Try to extract the assigned UID from the APPENDUID response
        # Response looks like: b'[APPENDUID 123456 789] APPEND completed'
        return _parse_appenduid(data)


def _get_drafts_folder() -> str:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'drafts_folder'"
        ).fetchone()
        return row["value"] if row else "Drafts"
    finally:
        conn.close()


def _build_mime(to: str, subject: str, body: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["From"] = settings.email_address
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
    msg.attach(MIMEText(body, "plain", "utf-8"))
    return msg


def _parse_appenduid(data: list) -> int | None:
    try:
        response_str = data[0].decode() if isinstance(data[0], bytes) else str(data[0])
        if "APPENDUID" in response_str:
            # e.g. "[APPENDUID 123456 789]"
            parts = response_str.split("APPENDUID")[1].split("]")[0].strip().split()
            return int(parts[1])
    except (IndexError, ValueError, AttributeError):
        pass
    return None
