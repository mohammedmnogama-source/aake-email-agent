"""
Extracts price quotes from emails using Claude.
Reads directly from IMAP so it covers ALL historical emails,
not just those already in the local database.
"""
import sqlite3

from imap_tools import A

from backend.ai.gemini_client import call_ai
from backend.ai.redactor import redact
from backend.database.repositories import prices as price_repo
from backend.email.fetcher import _strip_html
from backend.email.imap_client import get_mailbox

# Folders to skip — no pricing info expected there
_SKIP_FOLDER_KEYWORDS = ("trash", "junk", "spam", "draft", "sent", "deleted", "outbox")

# Max emails to pull per folder to avoid scanning forever
_MAX_PER_FOLDER = 500

PRICE_EXTRACTION_SYSTEM_PROMPT = """You are a pricing data extractor for an IT reseller in Kuwait.
Extract ALL price quotes, product listings, and cost information from the email below.

Return a JSON array (empty array [] if no prices found). Each item must match:
{
  "product_name": "Full product name",
  "part_number": "SKU / part number or null",
  "unit_price": 123.45 (number, no commas) or null if not stated,
  "currency": "USD",
  "quantity": 1 (number) or null,
  "vendor_name": "Vendor / distributor name or null",
  "vendor_email": "vendor@example.com or null",
  "category": "Cisco" | "Fortinet" | "HP" | "Microsoft" | "Lenovo" | "Dell" | "Aruba" | "Palo Alto" | "Other",
  "validity_date": "YYYY-MM-DD or null",
  "notes": "Any discount, lead time, EOL notice, or special condition — one line max or null"
}

Category rules (IMPORTANT — use the specific brand, not "Other"):
- Cisco: anything with "Cisco", "ASA", "Catalyst", "ISR", "Meraki", "Webex", "Nexus", "Firepower", "C9200", "C9300", "C9500", "SFP", model starts with "C" + numbers
- Fortinet/FortiGate: anything with "Fortinet", "FortiGate", "FortiSwitch", "FortiAP", "FortiAnalyzer", "FortiManager", "FortiClient", "FG-", "FS-", "FAP-", "FML-"
- HP: anything with "HPE", "HP", "ProLiant", "Aruba" (network), "DL3", "DL5", "DL8", "Gen10", "Gen11", "iLO", "StoreEver", "Nimble", "SimpliVity", "Synergy"
- Aruba: "Aruba", "ArubaOS", "ClearPass" — use "HP" category for Aruba since HPE owns it
- Microsoft: "Microsoft", "Windows Server", "Office 365", "Azure", "M365", "Exchange", "SQL Server", "CAL", "Windows"
- Lenovo: "Lenovo", "ThinkPad", "ThinkCentre", "ThinkStation", "ThinkSystem", "SR" servers
- Dell: "Dell", "PowerEdge", "OptiPlex", "Latitude", "Precision", "EMC", "PowerStore", "Vxrail"
- Palo Alto: "Palo Alto", "PAN-OS", "Panorama", "PA-", "Prisma"

Extract rules:
- Extract EVERY line item from price list tables — do not summarise or skip rows.
- If quantities have tiers (1-9 / 10-49), create one entry per tier.
- If currency is KWD, AED, SAR or another currency, use that exact currency code.
- Always set currency — default to "USD" only if truly unknown.
- Return ONLY the JSON array. No explanation, no markdown, no code fences."""


def _should_skip_folder(folder_name: str) -> bool:
    low = folder_name.lower()
    return any(kw in low for kw in _SKIP_FOLDER_KEYWORDS)


def extract_prices_from_all_imap(
    conn: sqlite3.Connection,
    progress_cb=None,
) -> dict:
    """
    Open IMAP, list every folder, fetch up to _MAX_PER_FOLDER recent messages
    per folder, extract prices from each one that hasn't been processed yet.
    progress_cb(processed, skipped, total_quotes, errors, current_folder) called after each email.
    Returns summary stats.
    """
    processed = 0
    skipped = 0
    total_quotes = 0
    errors = 0
    folders_scanned: list[str] = []

    with get_mailbox() as mb:
        all_folders = list(mb.folder.list())
        target_folders = [
            f.name for f in all_folders
            if not _should_skip_folder(f.name)
        ]
        if not target_folders:
            target_folders = ["INBOX"]

        print(f"[price_extractor] Folders to scan: {target_folders}")

        for folder_name in target_folders:
            try:
                mb.folder.set(folder_name)
            except Exception as e:
                print(f"[price_extractor] Cannot open folder {folder_name}: {e}")
                continue

            folders_scanned.append(folder_name)

            try:
                messages = sorted(
                    mb.fetch(A(all=True), mark_seen=False, bulk=True),
                    key=lambda m: int(m.uid),
                    reverse=True,
                )[:_MAX_PER_FOLDER]
            except Exception as e:
                print(f"[price_extractor] Fetch error in {folder_name}: {e}")
                continue

            print(f"[price_extractor] {folder_name}: {len(messages)} messages")

            for msg in messages:
                imap_uid = int(msg.uid)

                if price_repo.already_extracted_imap(conn, imap_uid, folder_name):
                    skipped += 1
                    if progress_cb:
                        progress_cb(processed, skipped, total_quotes, errors, folder_name)
                    continue

                body = msg.text or _strip_html(msg.html or "")
                if not body.strip():
                    price_repo.mark_no_prices(conn, imap_uid, folder_name)
                    skipped += 1
                    if progress_cb:
                        progress_cb(processed, skipped, total_quotes, errors, folder_name)
                    continue

                redacted_body, redact_count = redact(body)

                user_message = (
                    f"From: {msg.from_ or ''}\n"
                    f"Subject: {msg.subject or ''}\n\n"
                    f"{redacted_body[:6000]}"
                )

                try:
                    result, _, _ = call_ai(
                        system_prompt=PRICE_EXTRACTION_SYSTEM_PROMPT,
                        user_message=user_message,
                        purpose="price_extraction",
                        redactions_count=redact_count,
                        conn=conn,
                    )
                except Exception as e:
                    print(f"[price_extractor] Claude error uid={imap_uid}: {e}")
                    errors += 1
                    if progress_cb:
                        progress_cb(processed, skipped, total_quotes, errors, folder_name)
                    continue

                quotes = result if isinstance(result, list) else []
                quotes = [q for q in quotes if q.get("product_name")]

                try:
                    if quotes:
                        price_repo.insert_quotes(
                            conn,
                            quotes,
                            imap_uid=imap_uid,
                            folder_path=folder_name,
                            email_subject=msg.subject or "",
                            email_from=msg.from_ or "",
                        )
                        total_quotes += len(quotes)
                    else:
                        price_repo.mark_no_prices(conn, imap_uid, folder_name)
                except Exception as e:
                    print(f"[price_extractor] DB insert error uid={imap_uid}: {e}")
                    errors += 1

                processed += 1
                if progress_cb:
                    progress_cb(processed, skipped, total_quotes, errors, folder_name)

    return {
        "processed": processed,
        "skipped": skipped,
        "total_quotes": total_quotes,
        "errors": errors,
        "folders_scanned": folders_scanned,
    }


def extract_prices_from_email(conn: sqlite3.Connection, email_id: int) -> list[dict]:
    """Extract prices from a single DB email (used for re-run on a specific email)."""
    from backend.database.repositories.emails import get_by_id
    email = get_by_id(conn, email_id)
    if not email:
        return []
    body = email["body_text"] or ""
    if not body.strip():
        return []
    redacted_body, redact_count = redact(body)
    user_message = (
        f"From: {email['from_address']}\n"
        f"Subject: {email['subject']}\n\n"
        f"{redacted_body[:6000]}"
    )
    try:
        result, _, _ = call_ai(
            system_prompt=PRICE_EXTRACTION_SYSTEM_PROMPT,
            user_message=user_message,
            purpose="price_extraction",
            redactions_count=redact_count,
            email_id=email_id,
            conn=conn,
        )
    except Exception:
        return []
    quotes = result if isinstance(result, list) else []
    quotes = [q for q in quotes if q.get("product_name")]
    if quotes:
        price_repo.delete_by_email(conn, email_id)
        price_repo.insert_quotes(
            conn,
            quotes,
            email_id=email_id,
            email_subject=email["subject"],
            email_from=email["from_address"],
        )
    return quotes
