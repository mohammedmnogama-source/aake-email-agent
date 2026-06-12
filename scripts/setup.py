"""
First-run setup script.

Run from the project root:
    python scripts/setup.py

What it does:
1. Reads credentials from .env
2. Tests IMAP connection
3. Lists all server folders, finds "AI Agent" and "Drafts" exact paths
4. Stores those paths in settings table
5. Inserts imap_sync seed row for the target folder
6. Prompts for a dashboard password and stores the bcrypt hash
7. Runs DB migrations
"""

import sys
from pathlib import Path

# allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from getpass import getpass

import bcrypt
from imap_tools import MailBox, MailboxLoginError

from backend.config import settings
from backend.database.connection import get_connection, init_db


def find_folder(mailbox: MailBox, target_name: str) -> str | None:
    """
    Return the exact server-side folder path matching target_name (case-insensitive).
    Handles cPanel's INBOX. prefix convention — matches on the last path segment.
    e.g. target_name="AI Agent" matches server folder "INBOX.AI Agent".
    """
    target_lower = target_name.lower()
    for folder in mailbox.folder.list():
        name = folder.name
        # Match full name or last segment after the final separator
        last_segment = name.split(".")[-1].lower()
        if name.lower() == target_lower or last_segment == target_lower:
            return name
    return None


def update_setting(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
        (key, value),
    )


def main() -> None:
    print("=== AAKE Email Agent — First-Run Setup ===\n")

    # 1. Init DB (runs migrations)
    init_db(settings.database_path)
    print(f"[ok] Database ready at {settings.database_path}")

    # 2. Test IMAP connection
    print(f"\nConnecting to {settings.imap_host}:{settings.imap_port} as {settings.email_address}...")
    try:
        with MailBox(settings.imap_host, port=settings.imap_port).login(
            settings.email_address, settings.email_password
        ) as mailbox:
            print("[ok] IMAP login successful")

            # 3. List all folders
            all_folders = list(mailbox.folder.list())
            print(f"\nFolders found on server ({len(all_folders)} total):")
            for f in all_folders:
                print(f"  • {f.name}")

            # 4. Find target folder
            ai_folder = find_folder(mailbox, "AI Agent")
            if not ai_folder:
                print("\n[!] 'AI Agent' folder not found. Creating it...")
                mailbox.folder.create("INBOX.AI Agent")
                ai_folder = find_folder(mailbox, "AI Agent")
                if ai_folder:
                    print(f"[ok] Created: {ai_folder}")
                else:
                    print("[error] Could not create 'AI Agent' folder. Create it manually in webmail.")
                    sys.exit(1)
            else:
                print(f"\n[ok] Target folder found: '{ai_folder}'")

            # 5. Find Drafts folder
            drafts_folder = (
                find_folder(mailbox, "Drafts")
                or find_folder(mailbox, "INBOX.Drafts")
                or find_folder(mailbox, "Draft")
            )
            if not drafts_folder:
                print("[error] Could not find a Drafts folder. Check your webmail and note the exact name.")
                sys.exit(1)
            print(f"[ok] Drafts folder found: '{drafts_folder}'")

    except MailboxLoginError as e:
        print(f"\n[error] IMAP login failed: {e}")
        print("Check EMAIL_ADDRESS and EMAIL_PASSWORD in your .env file.")
        sys.exit(1)

    # 6. Update settings in DB
    conn = get_connection()
    try:
        update_setting(conn, "target_folder", ai_folder)
        update_setting(conn, "drafts_folder", drafts_folder)
        conn.commit()
        print(f"\n[ok] Settings updated — target_folder='{ai_folder}', drafts_folder='{drafts_folder}'")

        # 7. Seed imap_sync row for target folder
        conn.execute(
            "INSERT OR IGNORE INTO imap_sync (folder_path, last_uid) VALUES (?, 0)",
            (ai_folder,),
        )
        conn.commit()
        print(f"[ok] IMAP sync tracking initialised for '{ai_folder}'")

        # 8. Dashboard password
        print("\n--- Dashboard Password Setup ---")
        existing_pw = conn.execute(
            "SELECT value FROM settings WHERE key = 'dashboard_password'"
        ).fetchone()
        if existing_pw and existing_pw["value"]:
            reset = input("A dashboard password is already set. Reset it? [y/N]: ").strip().lower()
            if reset != "y":
                print("[skip] Keeping existing password.")
            else:
                _set_password(conn)
        else:
            _set_password(conn)
    finally:
        conn.close()

    print("\n=== Setup complete ===")
    print("Next step: run the agent with:")
    print("  uvicorn backend.main:app --reload\n")


def _set_password(conn) -> None:
    while True:
        pw = getpass("Enter dashboard password: ")
        pw2 = getpass("Confirm password: ")
        if pw != pw2:
            print("[error] Passwords do not match. Try again.")
            continue
        if len(pw) < 8:
            print("[error] Password must be at least 8 characters.")
            continue
        hashed = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        conn.execute(
            "INSERT INTO settings (key, value, description) VALUES ('dashboard_password', ?, 'bcrypt hash') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
            (hashed,),
        )
        conn.commit()
        print("[ok] Dashboard password set.")
        break


if __name__ == "__main__":
    main()
