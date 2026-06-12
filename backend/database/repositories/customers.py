import sqlite3
from typing import Optional


def list_customers(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM customers ORDER BY name ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_customer(conn: sqlite3.Connection, customer_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM customers WHERE id = ?", (customer_id,)
    ).fetchone()
    return dict(row) if row else None


def create_customer(conn: sqlite3.Connection, data: dict) -> dict:
    cur = conn.execute(
        """INSERT INTO customers (name, company, email, phone, country, notes)
           VALUES (:name, :company, :email, :phone, :country, :notes)""",
        {
            "name": data["name"],
            "company": data.get("company"),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "country": data.get("country", "Kuwait"),
            "notes": data.get("notes"),
        },
    )
    conn.commit()
    return get_customer(conn, cur.lastrowid)


def update_customer(conn: sqlite3.Connection, customer_id: int, data: dict) -> Optional[dict]:
    conn.execute(
        """UPDATE customers
           SET name    = COALESCE(:name, name),
               company = COALESCE(:company, company),
               email   = COALESCE(:email, email),
               phone   = COALESCE(:phone, phone),
               country = COALESCE(:country, country),
               notes   = COALESCE(:notes, notes),
               updated_at = datetime('now')
           WHERE id = :id""",
        {**data, "id": customer_id},
    )
    conn.commit()
    return get_customer(conn, customer_id)


def delete_customer(conn: sqlite3.Connection, customer_id: int) -> bool:
    cur = conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    conn.commit()
    return cur.rowcount > 0
