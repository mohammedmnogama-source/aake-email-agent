"""
backend/ai/trust.py — Category trust helpers.

Called by:
  - inbox approve endpoint (after Mo approves a draft)
  - analyzer auto-finish check (after storing a new suggestion)
"""

import re
import sqlite3
from datetime import datetime, timezone

# Categories that can NEVER earn trust — no auto-finish ever
_UNTRUSTED_CATEGORIES = {"vendor_quote_request", "internal", "spam"}

# Regex that catches any price/amount in a draft — if found, never auto-finish
_PRICE_PATTERN = re.compile(
    r'(KWD|USD|AED|KD|\$|€|£|\bprice\b|\btotal\b|\bamount\b)',
    re.IGNORECASE
)


def update_trust_streak(conn: sqlite3.Connection, category: str, was_edited: int) -> None:
    """
    Called after every approval.  Updates the category_trust row for `category`.
    Unedited approval → streak+1.  Edited approval → streak reset to 0.
    When streak reaches the threshold, marks category as trusted.
    """
    if not category:
        return

    # Get current row or create it
    row = conn.execute(
        "SELECT streak, trusted, total_approved, total_edited FROM category_trust WHERE category = ?",
        (category,)
    ).fetchone()

    if row:
        streak = row["streak"]
        total_approved = row["total_approved"]
        total_edited = row["total_edited"]
    else:
        streak = 0
        total_approved = 0
        total_edited = 0

    total_approved += 1
    if was_edited:
        streak = 0
        total_edited += 1
    else:
        streak += 1

    # Check threshold
    threshold_row = conn.execute(
        "SELECT value FROM settings WHERE key = 'trust_threshold'"
    ).fetchone()
    threshold = int(threshold_row["value"]) if threshold_row else 10

    now_trusted = 1 if streak >= threshold else 0
    trusted_at = datetime.now(timezone.utc).isoformat() if (now_trusted and not (row and row["trusted"])) else (row["trusted_at"] if row else None)

    conn.execute(
        """
        INSERT INTO category_trust (category, streak, trusted, trusted_at, total_approved, total_edited)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(category) DO UPDATE SET
            streak = excluded.streak,
            trusted = excluded.trusted,
            trusted_at = CASE WHEN excluded.trusted = 1 AND category_trust.trusted = 0
                              THEN excluded.trusted_at
                              ELSE category_trust.trusted_at END,
            total_approved = excluded.total_approved,
            total_edited = excluded.total_edited
        """,
        (category, streak, now_trusted, trusted_at, total_approved, total_edited)
    )


def is_category_trusted(conn: sqlite3.Connection, category: str) -> bool:
    """Returns True if this category has earned trust and can be auto-finished."""
    if category in _UNTRUSTED_CATEGORIES:
        return False
    row = conn.execute(
        "SELECT trusted FROM category_trust WHERE category = ?", (category,)
    ).fetchone()
    return bool(row and row["trusted"])


def draft_has_prices(draft: str) -> bool:
    """Returns True if the draft contains price-like content — block auto-finish."""
    return bool(_PRICE_PATTERN.search(draft or ""))


def revoke_trust(conn: sqlite3.Connection, category: str) -> None:
    """Mo revokes trust for a category — resets streak and trusted flag."""
    conn.execute(
        "UPDATE category_trust SET trusted = 0, streak = 0, trusted_at = NULL WHERE category = ?",
        (category,)
    )
