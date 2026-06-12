CREATE TABLE IF NOT EXISTS price_quotes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id      INTEGER REFERENCES emails(id) ON DELETE SET NULL,
    product_name  TEXT    NOT NULL,
    part_number   TEXT,
    unit_price    REAL,
    currency      TEXT    NOT NULL DEFAULT 'USD',
    quantity      INTEGER,
    vendor_name   TEXT,
    vendor_email  TEXT,
    category      TEXT,
    validity_date TEXT,
    notes         TEXT,
    extracted_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_price_quotes_category ON price_quotes(category);
CREATE INDEX IF NOT EXISTS idx_price_quotes_email_id ON price_quotes(email_id);
