"""
Scans all IMAP folders to build a contacts list from From/To/CC headers.
Also seeds from existing vendor_email values in price_quotes.
"""
import sqlite3

from imap_tools import A

from backend.email.imap_client import get_mailbox

_SKIP_KEYWORDS = ("trash", "junk", "spam", "deleted")
_OWN_DOMAINS = ("aqeeqkw.com",)
_MAX_PER_FOLDER = 1000


def _is_own_address(email: str) -> bool:
    email = email.lower()
    return any(d in email for d in _OWN_DOMAINS)


def _upsert(conn: sqlite3.Connection, email: str, name: str | None, source: str) -> None:
    email = email.strip().lower()
    if not email or "@" not in email:
        return
    existing = conn.execute(
        "SELECT id, display_name, frequency FROM contacts WHERE email = ?", (email,)
    ).fetchone()
    if existing:
        new_name = existing["display_name"] or name
        conn.execute(
            "UPDATE contacts SET frequency = frequency + 1, last_seen = datetime('now'), "
            "display_name = COALESCE(?, display_name) WHERE email = ?",
            (name if name and not existing["display_name"] else None, email),
        )
    else:
        conn.execute(
            "INSERT INTO contacts (email, display_name, frequency, source) VALUES (?, ?, 1, ?)",
            (email, name or None, source),
        )


def scan_contacts(conn: sqlite3.Connection, progress_cb=None) -> dict:
    """
    Walk all non-spam IMAP folders, extract From/To/CC addresses.
    Also pulls vendor emails from price_quotes.
    Returns summary stats.
    """
    total = 0
    folders_done = []

    # Seed from price_quotes vendor emails first
    rows = conn.execute(
        "SELECT DISTINCT vendor_email, vendor_name FROM price_quotes "
        "WHERE vendor_email IS NOT NULL AND vendor_email != ''"
    ).fetchall()
    for r in rows:
        _upsert(conn, r["vendor_email"], r["vendor_name"], "vendor")
    conn.commit()

    with get_mailbox() as mb:
        all_folders = list(mb.folder.list())
        target = [
            f.name for f in all_folders
            if not any(kw in f.name.lower() for kw in _SKIP_KEYWORDS)
        ]

        for folder_name in target:
            try:
                mb.folder.set(folder_name)
            except Exception:
                continue

            try:
                messages = list(mb.fetch(A(all=True), mark_seen=False, bulk=True,
                                          headers_only=True))
            except Exception:
                continue

            folders_done.append(folder_name)

            for msg in messages:
                try:
                    for addr in (msg.from_values,):
                        if addr and not _is_own_address(addr.email):
                            _upsert(conn, addr.email, addr.name or None, "from")
                    for addr in list(msg.to_values) + list(msg.cc_values):
                        if addr and not _is_own_address(addr.email):
                            _upsert(conn, addr.email, addr.name or None, "to")
                    total += 1
                except Exception:
                    pass

            conn.commit()
            if progress_cb:
                progress_cb(total, folder_name)

    return {"contacts_found": total, "folders_scanned": folders_done}


def search_contacts(conn: sqlite3.Connection, q: str, limit: int = 10) -> list[dict]:
    q = f"%{q.lower()}%"
    rows = conn.execute(
        """SELECT email, display_name, frequency FROM contacts
           WHERE lower(email) LIKE ? OR lower(coalesce(display_name,'')) LIKE ?
           ORDER BY frequency DESC LIMIT ?""",
        (q, q, limit),
    ).fetchall()
    return [{"email": r["email"], "name": r["display_name"], "frequency": r["frequency"]}
            for r in rows]


def list_all_contacts(conn: sqlite3.Connection, limit: int = 500) -> list[dict]:
    rows = conn.execute(
        "SELECT email, display_name, frequency, source FROM contacts "
        "ORDER BY frequency DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [{"email": r["email"], "name": r["display_name"],
             "frequency": r["frequency"], "source": r["source"]} for r in rows]
