-- Migration 008: Major redesign — paste/PDF input, task checklist, RFQ tracking
-- Rebuilds emails table (imap_uid nullable), adds input_batches, suggested_tasks,
-- reference_counters, rfqs, supplier_requests, quotations.
-- Also adds summary column to ai_suggestions.

-- -----------------------------------------------------------------------
-- Step 1: Create input_batches FIRST (emails.batch_id references it)
-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS input_batches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    submitted_at TEXT    NOT NULL DEFAULT (datetime('now')),
    status       TEXT    NOT NULL DEFAULT 'pending'
                 CHECK(status IN ('pending','processing','done','failed')),
    total_emails INTEGER NOT NULL DEFAULT 0,
    processed    INTEGER NOT NULL DEFAULT 0,
    error_msg    TEXT
);

-- -----------------------------------------------------------------------
-- Step 2: Rebuild emails table so imap_uid is nullable (paste/PDF have no UID)
-- SQLite does not support ALTER COLUMN, so we rename + recreate.
-- -----------------------------------------------------------------------

ALTER TABLE emails RENAME TO emails_v7;

CREATE TABLE emails (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    imap_uid        INTEGER,                          -- NULL for paste/PDF input
    folder_path     TEXT    NOT NULL DEFAULT 'paste',
    subject         TEXT,
    from_address    TEXT,
    from_name       TEXT,
    to_addresses    TEXT,
    cc_addresses    TEXT,
    body_text       TEXT,
    body_preview    TEXT,
    received_at     TEXT,
    fetched_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    has_attachments INTEGER NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK(status IN (
                        'pending','processing','decided','parse_error','error',
                        'clarification_pending','skipped','manually_handled'
                    )),
    batch_id        INTEGER REFERENCES input_batches(id),
    source          TEXT    NOT NULL DEFAULT 'imap'
                    CHECK(source IN ('imap','paste','pdf')),
    user_instruction TEXT,                            -- Mode 2: Mo's explicit instruction
    UNIQUE(imap_uid, folder_path)                     -- NULLs are distinct in SQLite UNIQUE
);

INSERT INTO emails (
    id, imap_uid, folder_path, subject, from_address, from_name,
    to_addresses, cc_addresses, body_text, body_preview, received_at,
    fetched_at, has_attachments, status,
    batch_id, source, user_instruction
)
SELECT
    id, imap_uid, folder_path, subject, from_address, from_name,
    to_addresses, cc_addresses, body_text, body_preview, received_at,
    fetched_at, has_attachments, status,
    NULL, 'imap', NULL
FROM emails_v7;

DROP TABLE emails_v7;

-- -----------------------------------------------------------------------
-- Step 3: suggested_tasks — replaces single suggested_action per email
-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS suggested_tasks (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id           INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    suggestion_id      INTEGER NOT NULL REFERENCES ai_suggestions(id) ON DELETE CASCADE,
    sequence_order     INTEGER NOT NULL DEFAULT 0,
    task_type          TEXT    NOT NULL,
    description        TEXT    NOT NULL,
    payload            TEXT,            -- JSON blob e.g. {"vendor_hint": "Cisco"}
    approved           INTEGER NOT NULL DEFAULT 0,
    depends_on_task_id INTEGER REFERENCES suggested_tasks(id),
    executed_at        TEXT,
    created_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------------------
-- Step 5: reference_counters — atomic RFQ/SQ/QT numbers
-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS reference_counters (
    prefix   TEXT    PRIMARY KEY,   -- 'RFQ', 'SQ', 'QT'
    year     INTEGER NOT NULL,
    last_seq INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO reference_counters VALUES ('RFQ', 2026, 0);
INSERT OR IGNORE INTO reference_counters VALUES ('SQ',  2026, 0);
INSERT OR IGNORE INTO reference_counters VALUES ('QT',  2026, 0);

-- -----------------------------------------------------------------------
-- Step 6: RFQ tracking tables
-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rfqs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number TEXT    NOT NULL UNIQUE,   -- RFQ-2026-0001
    email_id   INTEGER REFERENCES emails(id),
    customer   TEXT,
    description TEXT,
    status     TEXT    NOT NULL DEFAULT 'open'
               CHECK(status IN ('open','sent_to_suppliers','quoted','won','lost','cancelled')),
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS supplier_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number   TEXT    NOT NULL UNIQUE,   -- SQ-2026-0001-A
    rfq_id       INTEGER NOT NULL REFERENCES rfqs(id),
    vendor_id    INTEGER REFERENCES vendors(id),
    vendor_email TEXT,
    vendor_name  TEXT,
    status       TEXT    NOT NULL DEFAULT 'draft'
                 CHECK(status IN ('draft','sent','replied','no_response')),
    sent_at      TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quotations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number          TEXT    NOT NULL UNIQUE,   -- QT-2026-0001
    supplier_request_id INTEGER NOT NULL REFERENCES supplier_requests(id),
    rfq_id              INTEGER NOT NULL REFERENCES rfqs(id),
    total_amount        REAL,
    currency            TEXT    DEFAULT 'KWD',
    valid_until         TEXT,
    notes               TEXT,
    status              TEXT    NOT NULL DEFAULT 'received'
                        CHECK(status IN ('received','presented','accepted','rejected')),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------------------
-- Step 7: summary column already in 000_baseline_rebuilt.sql — no ALTER needed.
-- -----------------------------------------------------------------------
