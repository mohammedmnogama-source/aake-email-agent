import json
from datetime import timezone, date as _date, timedelta

import bleach
from imap_tools import A, MailMessage

# On the FIRST sync of a folder (no prior UID recorded), only pull emails from
# the last N days — so switching to a big mailbox like INBOX doesn't fetch and
# AI-analyze years of history. After that, syncing is incremental by UID.
_FIRST_SYNC_DAYS = 2

from backend.database.connection import get_connection
from backend.email.imap_client import get_mailbox
from backend.email.models import EmailAddress, RawEmail
from backend import sync_tracker

_PREVIEW_LENGTH = 300


def fetch_new_emails() -> list[int]:
    """
    Fetch emails with UID > last_uid from the monitored folder.
    Inserts new rows into the emails table and updates imap_sync.
    Returns a list of newly inserted email IDs (primary keys).
    """
    conn = get_connection()
    try:
        folder_path, last_uid = _get_sync_state(conn)
        if not folder_path:
            print("[fetcher] No target folder configured. Run scripts/setup.py first.")
            return []

        new_email_ids: list[int] = []

        sync_tracker._update(message=f"Checking folder '{folder_path}' for new emails...")

        with get_mailbox() as mb:
            mb.folder.set(folder_path)
            if last_uid == 0:
                # First time syncing this folder: only pull the last few days, then
                # baseline to the folder's current highest UID so later syncs are
                # incremental (avoids fetching the entire mailbox history).
                since = _date.today() - timedelta(days=_FIRST_SYNC_DAYS)
                messages = list(mb.fetch(A(date_gte=since), mark_seen=False))
                existing_uids = mb.uids()
                baseline_uid = max((int(u) for u in existing_uids), default=0)
            else:
                messages = list(mb.fetch(A(uid=f"{last_uid + 1}:*"), mark_seen=False))
                baseline_uid = last_uid

        if not messages:
            sync_tracker._update(message="No new emails found.")
            _update_sync(conn, folder_path, baseline_uid, 0)
            return []

        sync_tracker._update(message=f"Found {len(messages)} new email(s) — saving to database...")

        max_uid = baseline_uid
        for msg in messages:
            uid = int(msg.uid)
            raw = _parse_message(msg, folder_path)
            email_id = _insert_email(conn, raw)
            if email_id is not None:
                new_email_ids.append(email_id)
            if uid > max_uid:
                max_uid = uid

        _update_sync(conn, folder_path, max_uid, len(new_email_ids))
        conn.commit()
        sync_tracker.set_fetching(len(new_email_ids))
        print(f"[fetcher] Fetched {len(new_email_ids)} new email(s) from '{folder_path}'")
        return new_email_ids

    finally:
        conn.close()


def _get_sync_state(conn) -> tuple[str, int]:
    row = conn.execute(
        "SELECT s.value AS folder_path, i.last_uid "
        "FROM settings s "
        "LEFT JOIN imap_sync i ON i.folder_path = s.value "
        "WHERE s.key = 'target_folder'"
    ).fetchone()
    if not row:
        return "", 0
    return row["folder_path"], row["last_uid"] or 0


def _update_sync(conn, folder_path: str, last_uid: int, count: int) -> None:
    conn.execute(
        "INSERT INTO imap_sync (folder_path, last_uid, last_synced_at, last_count) "
        "VALUES (?, ?, datetime('now'), ?) "
        "ON CONFLICT(folder_path) DO UPDATE SET "
        "last_uid = excluded.last_uid, "
        "last_synced_at = excluded.last_synced_at, "
        "last_count = excluded.last_count",
        (folder_path, last_uid, count),
    )


def _parse_message(msg: MailMessage, folder_path: str) -> RawEmail:
    body_text = msg.text or _strip_html(msg.html or "")
    body_preview = body_text[:_PREVIEW_LENGTH].strip()

    received_at = (
        msg.date.astimezone(timezone.utc).isoformat()
        if msg.date
        else ""
    )

    from_addr = msg.from_ or ""
    from_name = msg.from_values.name if msg.from_values else ""

    to_list = [
        EmailAddress(email=a.email, name=a.name or "")
        for a in (msg.to_values or [])
    ]
    cc_list = [
        EmailAddress(email=a.email, name=a.name or "")
        for a in (msg.cc_values or [])
    ]

    return RawEmail(
        imap_uid=int(msg.uid),
        folder_path=folder_path,
        subject=msg.subject or "(no subject)",
        from_address=from_addr,
        from_name=from_name,
        to_addresses=to_list,
        cc_addresses=cc_list,
        body_text=body_text,
        body_preview=body_preview,
        received_at=received_at,
        has_attachments=bool(msg.attachments),
    )


def _insert_email(conn, raw: RawEmail) -> int | None:
    """Insert email row. Returns new row id, or None if duplicate."""
    existing = conn.execute(
        "SELECT id FROM emails WHERE imap_uid = ? AND folder_path = ?",
        (raw.imap_uid, raw.folder_path),
    ).fetchone()
    if existing:
        return None

    cursor = conn.execute(
        """INSERT INTO emails
           (imap_uid, folder_path, subject, from_address, from_name,
            to_addresses, cc_addresses, body_text, body_preview,
            received_at, has_attachments, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (
            raw.imap_uid,
            raw.folder_path,
            raw.subject,
            raw.from_address,
            raw.from_name,
            json.dumps([a.model_dump() for a in raw.to_addresses]),
            json.dumps([a.model_dump() for a in raw.cc_addresses]),
            raw.body_text,
            raw.body_preview,
            raw.received_at,
            int(raw.has_attachments),
        ),
    )
    return cursor.lastrowid


def _strip_html(html: str) -> str:
    return bleach.clean(html, tags=[], strip=True).strip()
