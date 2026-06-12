-- ============================================================
-- 000_baseline_rebuilt.sql
-- Replaces lost migrations 001, 004, 007, 008, 009.
-- Rebuilt 2026-06-12 from live DB schema.
--
-- All CREATE TABLE statements use IF NOT EXISTS so this is
-- safe to apply to the existing live DB (tables already exist
-- and are silently skipped).
--
-- IMPORTANT: Columns added by ALTER TABLE in later migrations
-- are NOT included here so those migrations still run cleanly
-- on a fresh DB:
--   - emails: rag_indexed (011), is_read (012)
--   - deals:  customer_id (010)
-- price_quotes is handled entirely by migrations 005 + 006.
-- ============================================================

-- Core lookup / config tables (no FK deps) ------------------

CREATE TABLE IF NOT EXISTS vendors (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL,
    company             TEXT    NOT NULL,
    email               TEXT    NOT NULL,
    phone               TEXT,
    brands              TEXT,
    product_categories  TEXT,
    notes               TEXT,
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS imap_sync (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_path     TEXT    NOT NULL UNIQUE,
    last_uid        INTEGER NOT NULL DEFAULT 0,
    last_synced_at  TEXT,
    last_count      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS writing_style (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_json TEXT    NOT NULL,
    email_count  INTEGER NOT NULL,
    confirmed    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS style_examples (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject      TEXT,
    body_preview TEXT,
    body_full    TEXT    NOT NULL,
    context_type TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS manually_handled_patterns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    from_domain   TEXT    NOT NULL,
    category      TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(from_domain, category)
);

CREATE TABLE IF NOT EXISTS contacts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    email        TEXT    NOT NULL UNIQUE,
    display_name TEXT,
    frequency    INTEGER NOT NULL DEFAULT 1,
    last_seen    TEXT    NOT NULL DEFAULT (datetime('now')),
    source       TEXT
);

CREATE INDEX IF NOT EXISTS idx_contacts_email     ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_contacts_frequency ON contacts(frequency DESC);

-- input_batches MUST come before emails (emails.batch_id FK) -

CREATE TABLE IF NOT EXISTS input_batches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    submitted_at TEXT    NOT NULL DEFAULT (datetime('now')),
    status       TEXT    NOT NULL DEFAULT 'pending'
                 CHECK(status IN ('pending','processing','done','failed')),
    total_emails INTEGER NOT NULL DEFAULT 0,
    processed    INTEGER NOT NULL DEFAULT 0,
    error_msg    TEXT
);

-- Core email table (WITHOUT rag_indexed and is_read — added by 011 and 012) -

CREATE TABLE IF NOT EXISTS emails (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    imap_uid        INTEGER,
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
    user_instruction TEXT,
    UNIQUE(imap_uid, folder_path)
);

-- Reference number sequences -----------------------------------

CREATE TABLE IF NOT EXISTS reference_counters (
    prefix   TEXT    PRIMARY KEY,
    year     INTEGER NOT NULL,
    last_seq INTEGER NOT NULL DEFAULT 0
);

-- Legacy RFQ / quotation workflow (pre-deals era) -------------

CREATE TABLE IF NOT EXISTS rfqs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number  TEXT    NOT NULL UNIQUE,
    email_id    INTEGER REFERENCES emails(id),
    customer    TEXT,
    description TEXT,
    status      TEXT    NOT NULL DEFAULT 'open'
                CHECK(status IN ('open','sent_to_suppliers','quoted','won','lost','cancelled')),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS supplier_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number   TEXT    NOT NULL UNIQUE,
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
    ref_number          TEXT    NOT NULL UNIQUE,
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

-- AI pipeline tables ------------------------------------------

CREATE TABLE IF NOT EXISTS api_audit_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT    NOT NULL DEFAULT (datetime('now')),
    model            TEXT    NOT NULL,
    purpose          TEXT    NOT NULL,
    prompt_size      INTEGER NOT NULL,
    response_size    INTEGER NOT NULL,
    prompt_hash      TEXT    NOT NULL,
    redactions_count INTEGER NOT NULL DEFAULT 0,
    email_id         INTEGER REFERENCES emails(id)
);

CREATE TABLE IF NOT EXISTS ai_suggestions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id            INTEGER NOT NULL UNIQUE REFERENCES emails(id) ON DELETE CASCADE,
    model_used          TEXT    NOT NULL,
    category            TEXT    NOT NULL CHECK(category IN ('lead','vendor_quote_request','customer_inquiry','internal','spam','other')),
    suggested_action    TEXT    NOT NULL,
    reasoning           TEXT    NOT NULL,
    summary             TEXT,
    draft_subject       TEXT,
    draft_to            TEXT,
    draft_content       TEXT,
    extracted_data      TEXT,
    suggested_vendor_id INTEGER REFERENCES vendors(id),
    confidence_note     TEXT,
    raw_response        TEXT,
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    few_shot_count      INTEGER DEFAULT 0,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    needs_clarification INTEGER NOT NULL DEFAULT 0,
    clarification_type  TEXT,
    clarification_question TEXT,
    clarification_options  TEXT,
    suggested_recipients   TEXT,
    clarification_round    INTEGER NOT NULL DEFAULT 0,
    manually_handled       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id      INTEGER NOT NULL REFERENCES emails(id),
    suggestion_id INTEGER NOT NULL REFERENCES ai_suggestions(id),
    decision      TEXT    NOT NULL CHECK(decision IN ('approved','rejected','edited')),
    edited_content   TEXT,
    edited_subject   TEXT,
    edited_to        TEXT,
    rejection_reason TEXT,
    edit_notes       TEXT,
    decided_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS actions_taken (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL REFERENCES decisions(id),
    email_id    INTEGER NOT NULL REFERENCES emails(id),
    action_type TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','success','failed')),
    result_data    TEXT,
    error_message  TEXT,
    executed_at    TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id        INTEGER NOT NULL REFERENCES emails(id),
    action_id       INTEGER REFERENCES actions_taken(id),
    name            TEXT,
    company         TEXT,
    contact_email   TEXT,
    contact_phone   TEXT,
    request_summary TEXT,
    raw_extracted   TEXT,
    status          TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','contacted','qualified','closed','rejected')),
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clarification_responses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_id INTEGER NOT NULL REFERENCES ai_suggestions(id) ON DELETE CASCADE,
    email_id      INTEGER NOT NULL REFERENCES emails(id),
    round         INTEGER NOT NULL DEFAULT 1,
    mo_answer     TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS suggested_tasks (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id           INTEGER NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
    suggestion_id      INTEGER NOT NULL REFERENCES ai_suggestions(id) ON DELETE CASCADE,
    sequence_order     INTEGER NOT NULL DEFAULT 0,
    task_type          TEXT    NOT NULL,
    description        TEXT    NOT NULL,
    payload            TEXT,
    approved           INTEGER NOT NULL DEFAULT 0,
    depends_on_task_id INTEGER REFERENCES suggested_tasks(id),
    executed_at        TEXT,
    created_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Customers (also created by migration 010 with IF NOT EXISTS) -

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

-- Deals workflow (WITHOUT customer_id — added by migration 010) -

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

CREATE TABLE IF NOT EXISTS deal_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id      INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    product_name TEXT    NOT NULL,
    qty          INTEGER,
    specs        TEXT,
    notes        TEXT,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deal_supplier_requests (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number       TEXT    NOT NULL UNIQUE,
    deal_id          INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    vendor_id        INTEGER REFERENCES vendors(id),
    vendor_name      TEXT    NOT NULL,
    vendor_email     TEXT,
    status           TEXT    NOT NULL DEFAULT 'draft'
                     CHECK(status IN ('draft','sent','replied','no_response')),
    email_draft_text TEXT,
    sent_at          TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deal_supplier_quotes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number          TEXT    NOT NULL UNIQUE,
    deal_id             INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    supplier_request_id INTEGER REFERENCES deal_supplier_requests(id),
    vendor_name         TEXT,
    total_amount        REAL,
    currency            TEXT    NOT NULL DEFAULT 'KWD',
    valid_until         TEXT,
    notes               TEXT,
    raw_email_text      TEXT,
    status              TEXT    NOT NULL DEFAULT 'received'
                        CHECK(status IN ('received','selected','rejected')),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deal_customer_quotes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number       TEXT    NOT NULL UNIQUE,
    deal_id          INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    total_amount     REAL,
    currency         TEXT    NOT NULL DEFAULT 'KWD',
    valid_until      TEXT,
    notes            TEXT,
    email_draft_text TEXT,
    status           TEXT    NOT NULL DEFAULT 'draft'
                     CHECK(status IN ('draft','sent','accepted','rejected')),
    sent_at          TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deal_customer_pos (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number         TEXT    NOT NULL UNIQUE,
    deal_id            INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    customer_quote_id  INTEGER REFERENCES deal_customer_quotes(id),
    customer_po_number TEXT,
    amount             REAL,
    currency           TEXT    NOT NULL DEFAULT 'KWD',
    received_at        TEXT,
    notes              TEXT,
    created_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS deal_supplier_pos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_number          TEXT    NOT NULL UNIQUE,
    deal_id             INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    supplier_request_id INTEGER REFERENCES deal_supplier_requests(id),
    supplier_quote_id   INTEGER REFERENCES deal_supplier_quotes(id),
    vendor_name         TEXT,
    vendor_email        TEXT,
    aake_po_number      TEXT,
    amount              REAL,
    currency            TEXT    NOT NULL DEFAULT 'KWD',
    issued_at           TEXT,
    notes               TEXT,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Approved drafts (also created by migration 013 with IF NOT EXISTS) --

CREATE TABLE IF NOT EXISTS approved_drafts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id            INTEGER NOT NULL,
    email_subject       TEXT,
    email_from_name     TEXT,
    email_from_address  TEXT,
    email_category      TEXT,
    original_draft      TEXT,
    approved_content    TEXT NOT NULL,
    was_edited          INTEGER NOT NULL DEFAULT 0,
    approved_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);
