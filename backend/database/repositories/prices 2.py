import sqlite3


def insert_quotes(
    conn: sqlite3.Connection,
    quotes: list[dict],
    email_id: int | None = None,
    imap_uid: int | None = None,
    folder_path: str | None = None,
    email_subject: str | None = None,
    email_from: str | None = None,
) -> None:
    for q in quotes:
        conn.execute(
            """INSERT INTO price_quotes
               (email_id, imap_uid, folder_path, email_subject, email_from,
                product_name, part_number, unit_price, currency,
                quantity, vendor_name, vendor_email, category, validity_date, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                email_id,
                imap_uid,
                folder_path,
                email_subject,
                email_from,
                q.get("product_name", ""),
                q.get("part_number"),
                q.get("unit_price"),
                q.get("currency") or "USD",
                q.get("quantity"),
                q.get("vendor_name"),
                q.get("vendor_email"),
                q.get("category"),
                q.get("validity_date"),
                q.get("notes"),
            ),
        )
    conn.commit()


def delete_by_imap(conn: sqlite3.Connection, imap_uid: int, folder_path: str) -> None:
    conn.execute(
        "DELETE FROM price_quotes WHERE imap_uid = ? AND folder_path = ?",
        (imap_uid, folder_path),
    )
    conn.commit()


def delete_by_email(conn: sqlite3.Connection, email_id: int) -> None:
    conn.execute("DELETE FROM price_quotes WHERE email_id = ?", (email_id,))
    conn.commit()


def already_extracted_imap(
    conn: sqlite3.Connection, imap_uid: int, folder_path: str
) -> bool:
    row = conn.execute(
        "SELECT 1 FROM price_quotes WHERE imap_uid = ? AND folder_path = ? LIMIT 1",
        (imap_uid, folder_path),
    ).fetchone()
    return row is not None


def mark_no_prices(conn: sqlite3.Connection, imap_uid: int, folder_path: str) -> None:
    """Insert a sentinel row so this email isn't re-scanned (no prices found)."""
    conn.execute(
        """INSERT OR IGNORE INTO price_quotes
           (imap_uid, folder_path, product_name, currency)
           VALUES (?, ?, '__no_prices__', 'USD')""",
        (imap_uid, folder_path),
    )
    conn.commit()


def list_all(
    conn: sqlite3.Connection,
    category: str | None = None,
    vendor: str | None = None,
    search: str | None = None,
) -> list[sqlite3.Row]:
    conditions = ["product_name != '__no_prices__'"]
    params: list = []

    if category:
        conditions.append("category = ?")
        params.append(category)
    if vendor:
        conditions.append("(vendor_name LIKE ? OR email_from LIKE ?)")
        params.extend([f"%{vendor}%", f"%{vendor}%"])
    if search:
        conditions.append("(product_name LIKE ? OR part_number LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = "WHERE " + " AND ".join(conditions)

    return conn.execute(
        f"""SELECT pq.*,
               COALESCE(pq.email_subject, e.subject) AS effective_subject,
               COALESCE(pq.email_from, e.from_address) AS effective_from
            FROM price_quotes pq
            LEFT JOIN emails e ON pq.email_id = e.id
            {where}
            ORDER BY pq.extracted_at DESC""",
        params,
    ).fetchall()


def list_categories(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT category FROM price_quotes "
        "WHERE category IS NOT NULL AND product_name != '__no_prices__' ORDER BY category"
    ).fetchall()
    return [r[0] for r in rows]
