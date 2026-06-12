-- Migration 009: Deal management system
-- Adds deal tracking tables replacing the email-inbox model.
-- reference_counters table already exists from 008.

INSERT OR IGNORE INTO reference_counters VALUES ('DEAL', 2026, 0);
INSERT OR IGNORE INTO reference_counters VALUES ('SRQ',  2026, 0);
INSERT OR IGNORE INTO reference_counters VALUES ('SQ',   2026, 0);
INSERT OR IGNORE INTO reference_counters VALUES ('CQ',   2026, 0);
INSERT OR IGNORE INTO reference_counters VALUES ('CPO',  2026, 0);
INSERT OR IGNORE INTO reference_counters VALUES ('SPO',  2026, 0);

-- Core deal entity (one per customer inquiry)
CREATE TABLE IF NOT EXISTS deals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number      TEXT NOT NULL UNIQUE,
    status          TEXT NOT NULL DEFAULT 'inquiry'
                    CHECK(status IN ('inquiry','sourcing','quoted','negotiating','won','fulfilled','closed','lost','cancelled')),
    customer_name   TEXT NOT NULL,
    customer_email  TEXT,
    description     TEXT,
    source_type     TEXT NOT NULL DEFAULT 'manual'
                    CHECK(source_type IN ('manual','email_paste','pdf')),
    source_raw_text TEXT,
    ai_next_step    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Line items per deal (multiple products per inquiry)
CREATE TABLE IF NOT EXISTS deal_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id      INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    product_name TEXT NOT NULL,
    qty          INTEGER,
    specs        TEXT,
    notes        TEXT,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Supplier requests (one deal → multiple suppliers)
-- Note: create BEFORE any table that references it to avoid FK ordering errors
CREATE TABLE IF NOT EXISTS deal_supplier_requests (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number       TEXT NOT NULL UNIQUE,
    deal_id          INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    vendor_id        INTEGER REFERENCES vendors(id),
    vendor_name      TEXT NOT NULL,
    vendor_email     TEXT,
    status           TEXT NOT NULL DEFAULT 'draft'
                     CHECK(status IN ('draft','sent','replied','no_response')),
    email_draft_text TEXT,
    sent_at          TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Supplier quotes received
CREATE TABLE IF NOT EXISTS deal_supplier_quotes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number          TEXT NOT NULL UNIQUE,
    deal_id             INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    supplier_request_id INTEGER REFERENCES deal_supplier_requests(id),
    vendor_name         TEXT,
    total_amount        REAL,
    currency            TEXT NOT NULL DEFAULT 'KWD',
    valid_until         TEXT,
    notes               TEXT,
    raw_email_text      TEXT,
    status              TEXT NOT NULL DEFAULT 'received'
                        CHECK(status IN ('received','selected','rejected')),
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Customer quotations (what AAKE sends to customer)
CREATE TABLE IF NOT EXISTS deal_customer_quotes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number       TEXT NOT NULL UNIQUE,
    deal_id          INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    total_amount     REAL,
    currency         TEXT NOT NULL DEFAULT 'KWD',
    valid_until      TEXT,
    notes            TEXT,
    email_draft_text TEXT,
    status           TEXT NOT NULL DEFAULT 'draft'
                     CHECK(status IN ('draft','sent','accepted','rejected')),
    sent_at          TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Customer POs (from customer to AAKE)
CREATE TABLE IF NOT EXISTS deal_customer_pos (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number         TEXT NOT NULL UNIQUE,
    deal_id            INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    customer_quote_id  INTEGER REFERENCES deal_customer_quotes(id),
    customer_po_number TEXT,
    amount             REAL,
    currency           TEXT NOT NULL DEFAULT 'KWD',
    received_at        TEXT,
    notes              TEXT,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Supplier POs (from AAKE to supplier)
CREATE TABLE IF NOT EXISTS deal_supplier_pos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number          TEXT NOT NULL UNIQUE,
    deal_id             INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    supplier_request_id INTEGER REFERENCES deal_supplier_requests(id),
    supplier_quote_id   INTEGER REFERENCES deal_supplier_quotes(id),
    vendor_name         TEXT,
    vendor_email        TEXT,
    aake_po_number      TEXT,
    amount              REAL,
    currency            TEXT NOT NULL DEFAULT 'KWD',
    issued_at           TEXT,
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
