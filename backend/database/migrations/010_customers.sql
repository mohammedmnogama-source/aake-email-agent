-- Customer database so Mo doesn't retype customer details every deal
CREATE TABLE IF NOT EXISTS customers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    company      TEXT,
    email        TEXT,
    phone        TEXT,
    country      TEXT DEFAULT 'Kuwait',
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Link deals to customers (optional — existing deals stay intact)
ALTER TABLE deals ADD COLUMN customer_id INTEGER REFERENCES customers(id);
