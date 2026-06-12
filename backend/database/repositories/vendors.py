import json
import sqlite3


def create(conn: sqlite3.Connection, data: dict) -> int:
    cursor = conn.execute(
        """INSERT INTO vendors (name, company, email, phone, brands, product_categories, notes)
           VALUES (:name, :company, :email, :phone, :brands, :product_categories, :notes)""",
        {
            "name": data.get("name", ""),
            "company": data.get("company", ""),
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "brands": json.dumps(data.get("brands", [])),
            "product_categories": json.dumps(data.get("product_categories", [])),
            "notes": data.get("notes", ""),
        },
    )
    return cursor.lastrowid


def list_active(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM vendors WHERE is_active = 1 ORDER BY name"
    ).fetchall()


def list_all(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM vendors ORDER BY name").fetchall()


def get_by_id(conn: sqlite3.Connection, vendor_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()


def update(conn: sqlite3.Connection, vendor_id: int, data: dict) -> None:
    conn.execute(
        """UPDATE vendors SET name=:name, company=:company, email=:email, phone=:phone,
           brands=:brands, product_categories=:product_categories, notes=:notes,
           updated_at=datetime('now')
           WHERE id=:id""",
        {
            "id": vendor_id,
            "name": data.get("name", ""),
            "company": data.get("company", ""),
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "brands": json.dumps(data.get("brands", [])),
            "product_categories": json.dumps(data.get("product_categories", [])),
            "notes": data.get("notes", ""),
        },
    )


def soft_delete(conn: sqlite3.Connection, vendor_id: int) -> None:
    conn.execute(
        "UPDATE vendors SET is_active = 0, updated_at = datetime('now') WHERE id = ?",
        (vendor_id,),
    )
