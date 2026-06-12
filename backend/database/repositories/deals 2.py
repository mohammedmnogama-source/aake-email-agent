import json
import sqlite3


# ---------------------------------------------------------------------------
# Reference number helpers
# ---------------------------------------------------------------------------

def _next_ref(conn: sqlite3.Connection, prefix: str) -> str:
    """Generate next atomic reference number, e.g. DEAL-2026-0001."""
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        "SELECT year, last_seq FROM reference_counters WHERE prefix = ?", (prefix,)
    ).fetchone()
    new_seq = row["last_seq"] + 1
    conn.execute(
        "UPDATE reference_counters SET last_seq = ? WHERE prefix = ?",
        (new_seq, prefix),
    )
    conn.commit()
    return f"{prefix}-{row['year']}-{new_seq:04d}"


def _next_supplier_request_ref(conn: sqlite3.Connection, deal_id: int) -> str:
    """Generate SRQ-2026-0001-A, -B, -C etc. based on existing count for this deal."""
    count = conn.execute(
        "SELECT COUNT(*) FROM deal_supplier_requests WHERE deal_id = ?", (deal_id,)
    ).fetchone()[0]
    # Get the deal's ref number base (e.g. DEAL-2026-0001 → 0001)
    deal_row = conn.execute("SELECT ref_number FROM deals WHERE id = ?", (deal_id,)).fetchone()
    base = deal_row["ref_number"].replace("DEAL-", "SRQ-")
    letter = chr(65 + count)  # A=65, B=66 ...
    return f"{base}-{letter}"


# ---------------------------------------------------------------------------
# Deal CRUD
# ---------------------------------------------------------------------------

def list_deals(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT d.*,
               (SELECT COUNT(*) FROM deal_supplier_requests WHERE deal_id = d.id) AS supplier_request_count,
               (SELECT COUNT(*) FROM deal_supplier_quotes   WHERE deal_id = d.id) AS supplier_quote_count,
               (SELECT COUNT(*) FROM deal_customer_quotes   WHERE deal_id = d.id) AS customer_quote_count
        FROM deals d
        ORDER BY d.updated_at DESC
        """
    ).fetchall()


def get_deal(conn: sqlite3.Connection, deal_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()


def create_deal(
    conn: sqlite3.Connection,
    customer_name: str,
    customer_email: str | None = None,
    description: str | None = None,
    source_type: str = "manual",
    source_raw_text: str | None = None,
    customer_id: int | None = None,
) -> int:
    ref = _next_ref(conn, "DEAL")
    cur = conn.execute(
        """
        INSERT INTO deals (ref_number, customer_name, customer_email, description, source_type, source_raw_text, customer_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ref, customer_name, customer_email, description, source_type, source_raw_text, customer_id),
    )
    conn.commit()
    return cur.lastrowid


def update_deal(conn: sqlite3.Connection, deal_id: int, fields: dict) -> None:
    allowed = {"status", "customer_name", "customer_email", "description", "ai_next_step"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = "datetime('now')"
    set_clause = ", ".join(
        f"{k} = datetime('now')" if k == "updated_at" else f"{k} = ?"
        for k in updates
    )
    values = [v for k, v in updates.items() if k != "updated_at"]
    values.append(deal_id)
    conn.execute(f"UPDATE deals SET {set_clause} WHERE id = ?", values)
    conn.commit()


def delete_deal(conn: sqlite3.Connection, deal_id: int) -> None:
    conn.execute("DELETE FROM deals WHERE id = ?", (deal_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Deal items
# ---------------------------------------------------------------------------

def list_items(conn: sqlite3.Connection, deal_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM deal_items WHERE deal_id = ? ORDER BY sort_order, id", (deal_id,)
    ).fetchall()


def add_item(
    conn: sqlite3.Connection,
    deal_id: int,
    product_name: str,
    qty: int | None = None,
    specs: str | None = None,
    notes: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO deal_items (deal_id, product_name, qty, specs, notes) VALUES (?, ?, ?, ?, ?)",
        (deal_id, product_name, qty, specs, notes),
    )
    conn.commit()
    return cur.lastrowid


def update_item(conn: sqlite3.Connection, item_id: int, fields: dict) -> None:
    allowed = {"product_name", "qty", "specs", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [item_id]
    conn.execute(f"UPDATE deal_items SET {set_clause} WHERE id = ?", values)
    conn.commit()


def delete_item(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM deal_items WHERE id = ?", (item_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Supplier requests
# ---------------------------------------------------------------------------

def list_supplier_requests(conn: sqlite3.Connection, deal_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM deal_supplier_requests WHERE deal_id = ? ORDER BY id", (deal_id,)
    ).fetchall()


def create_supplier_request(
    conn: sqlite3.Connection,
    deal_id: int,
    vendor_name: str,
    vendor_email: str | None = None,
    vendor_id: int | None = None,
    email_draft_text: str | None = None,
) -> int:
    ref = _next_supplier_request_ref(conn, deal_id)
    cur = conn.execute(
        """
        INSERT INTO deal_supplier_requests
            (ref_number, deal_id, vendor_id, vendor_name, vendor_email, email_draft_text)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (ref, deal_id, vendor_id, vendor_name, vendor_email, email_draft_text),
    )
    conn.commit()
    return cur.lastrowid


def update_supplier_request(conn: sqlite3.Connection, sr_id: int, fields: dict) -> None:
    allowed = {"status", "vendor_email", "email_draft_text", "sent_at"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [sr_id]
    conn.execute(f"UPDATE deal_supplier_requests SET {set_clause} WHERE id = ?", values)
    conn.commit()


# ---------------------------------------------------------------------------
# Supplier quotes
# ---------------------------------------------------------------------------

def list_supplier_quotes(conn: sqlite3.Connection, deal_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM deal_supplier_quotes WHERE deal_id = ? ORDER BY id", (deal_id,)
    ).fetchall()


def create_supplier_quote(
    conn: sqlite3.Connection,
    deal_id: int,
    vendor_name: str | None = None,
    supplier_request_id: int | None = None,
    total_amount: float | None = None,
    currency: str = "KWD",
    valid_until: str | None = None,
    notes: str | None = None,
    raw_email_text: str | None = None,
) -> int:
    ref = _next_ref(conn, "SQ")
    cur = conn.execute(
        """
        INSERT INTO deal_supplier_quotes
            (ref_number, deal_id, supplier_request_id, vendor_name, total_amount, currency, valid_until, notes, raw_email_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ref, deal_id, supplier_request_id, vendor_name, total_amount, currency, valid_until, notes, raw_email_text),
    )
    conn.commit()
    return cur.lastrowid


def update_supplier_quote(conn: sqlite3.Connection, sq_id: int, fields: dict) -> None:
    allowed = {"status", "total_amount", "currency", "valid_until", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [sq_id]
    conn.execute(f"UPDATE deal_supplier_quotes SET {set_clause} WHERE id = ?", values)
    conn.commit()


# ---------------------------------------------------------------------------
# Customer quotes
# ---------------------------------------------------------------------------

def list_customer_quotes(conn: sqlite3.Connection, deal_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM deal_customer_quotes WHERE deal_id = ? ORDER BY id", (deal_id,)
    ).fetchall()


def create_customer_quote(
    conn: sqlite3.Connection,
    deal_id: int,
    total_amount: float | None = None,
    currency: str = "KWD",
    valid_until: str | None = None,
    notes: str | None = None,
    email_draft_text: str | None = None,
) -> int:
    ref = _next_ref(conn, "CQ")
    cur = conn.execute(
        """
        INSERT INTO deal_customer_quotes
            (ref_number, deal_id, total_amount, currency, valid_until, notes, email_draft_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ref, deal_id, total_amount, currency, valid_until, notes, email_draft_text),
    )
    conn.commit()
    return cur.lastrowid


def update_customer_quote(conn: sqlite3.Connection, cq_id: int, fields: dict) -> None:
    allowed = {"status", "total_amount", "currency", "valid_until", "notes", "email_draft_text", "sent_at"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [cq_id]
    conn.execute(f"UPDATE deal_customer_quotes SET {set_clause} WHERE id = ?", values)
    conn.commit()


# ---------------------------------------------------------------------------
# Purchase orders
# ---------------------------------------------------------------------------

def create_customer_po(
    conn: sqlite3.Connection,
    deal_id: int,
    customer_quote_id: int | None = None,
    customer_po_number: str | None = None,
    amount: float | None = None,
    currency: str = "KWD",
    received_at: str | None = None,
    notes: str | None = None,
) -> int:
    ref = _next_ref(conn, "CPO")
    cur = conn.execute(
        """
        INSERT INTO deal_customer_pos
            (ref_number, deal_id, customer_quote_id, customer_po_number, amount, currency, received_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ref, deal_id, customer_quote_id, customer_po_number, amount, currency, received_at, notes),
    )
    conn.commit()
    return cur.lastrowid


def list_customer_pos(conn: sqlite3.Connection, deal_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM deal_customer_pos WHERE deal_id = ? ORDER BY id", (deal_id,)
    ).fetchall()


def create_supplier_po(
    conn: sqlite3.Connection,
    deal_id: int,
    supplier_request_id: int | None = None,
    supplier_quote_id: int | None = None,
    vendor_name: str | None = None,
    vendor_email: str | None = None,
    aake_po_number: str | None = None,
    amount: float | None = None,
    currency: str = "KWD",
    issued_at: str | None = None,
    notes: str | None = None,
) -> int:
    ref = _next_ref(conn, "SPO")
    cur = conn.execute(
        """
        INSERT INTO deal_supplier_pos
            (ref_number, deal_id, supplier_request_id, supplier_quote_id, vendor_name, vendor_email, aake_po_number, amount, currency, issued_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ref, deal_id, supplier_request_id, supplier_quote_id, vendor_name, vendor_email, aake_po_number, amount, currency, issued_at, notes),
    )
    conn.commit()
    return cur.lastrowid


def list_supplier_pos(conn: sqlite3.Connection, deal_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM deal_supplier_pos WHERE deal_id = ? ORDER BY id", (deal_id,)
    ).fetchall()


# ---------------------------------------------------------------------------
# Full deal detail (all related records in one call)
# ---------------------------------------------------------------------------

def get_deal_full(conn: sqlite3.Connection, deal_id: int) -> dict | None:
    deal = get_deal(conn, deal_id)
    if not deal:
        return None
    return {
        "deal": dict(deal),
        "items": [dict(r) for r in list_items(conn, deal_id)],
        "supplier_requests": [dict(r) for r in list_supplier_requests(conn, deal_id)],
        "supplier_quotes": [dict(r) for r in list_supplier_quotes(conn, deal_id)],
        "customer_quotes": [dict(r) for r in list_customer_quotes(conn, deal_id)],
        "customer_pos": [dict(r) for r in list_customer_pos(conn, deal_id)],
        "supplier_pos": [dict(r) for r in list_supplier_pos(conn, deal_id)],
    }
