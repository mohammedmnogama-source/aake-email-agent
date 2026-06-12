PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── emails ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS emails (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    imap_uid        INTEGER NOT NULL,
    folder_path     TEXT    NOT NULL,
    subject         TEXT,
    from_address    TEXT    NOT NULL,
    from_name       TEXT,
    to_addresses    TEXT    NOT NULL,       -- JSON array: [{"email":"..","name":".."}]
    cc_addresses    TEXT,                   -- JSON array, nullable
    body_text       TEXT,
    body_preview    TEXT,                   -- first 300 chars for list view
    received_at     TEXT    NOT NULL,       -- ISO 8601
    fetched_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    has_attachments INTEGER NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','processing','decided','parse_error','error')),
    UNIQUE(imap_uid, folder_path)
);

CREATE INDEX IF NOT EXISTS idx_emails_status      ON emails(status);
CREATE INDEX IF NOT EXISTS idx_emails_received_at ON emails(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_emails_from        ON emails(from_address);

-- ── ai_suggestions ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_suggestions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id            INTEGER NOT NULL UNIQUE REFERENCES emails(id) ON DELETE CASCADE,
    model_used          TEXT    NOT NULL,
    category            TEXT    NOT NULL
                        CHECK(category IN (
                            'lead','vendor_quote_request','customer_inquiry',
                            'internal','spam','other'
                        )),
    suggested_action    TEXT    NOT NULL
                        CHECK(suggested_action IN (
                            'draft_reply','forward_to_vendor',
                            'extract_lead_info','summarize_only','ignore'
                        )),
    reasoning           TEXT    NOT NULL,
    draft_subject       TEXT,
    draft_to            TEXT,
    draft_content       TEXT,
    extracted_data      TEXT,               -- JSON: {name,company,contact_email,contact_phone,request_summary}
    suggested_vendor_id INTEGER REFERENCES vendors(id),
    confidence_note     TEXT,
    raw_response        TEXT,               -- full raw Gemini JSON for debugging
    prompt_tokens       INTEGER,
    completion_tokens   INTEGER,
    few_shot_count      INTEGER DEFAULT 0,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── decisions ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decisions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id            INTEGER NOT NULL REFERENCES emails(id),
    suggestion_id       INTEGER NOT NULL REFERENCES ai_suggestions(id),
    decision            TEXT    NOT NULL
                        CHECK(decision IN ('approved','rejected','edited')),
    edited_content      TEXT,
    edited_subject      TEXT,
    edited_to           TEXT,
    rejection_reason    TEXT,               -- fed back as few-shot signal
    edit_notes          TEXT,
    decided_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_decisions_email_id   ON decisions(email_id);
CREATE INDEX IF NOT EXISTS idx_decisions_decided_at ON decisions(decided_at DESC);

-- ── actions_taken ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS actions_taken (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id     INTEGER NOT NULL REFERENCES decisions(id),
    email_id        INTEGER NOT NULL REFERENCES emails(id),
    action_type     TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','success','failed')),
    result_data     TEXT,                   -- JSON: {draft_uid, imap_folder, etc.}
    error_message   TEXT,
    executed_at     TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_actions_email_id   ON actions_taken(email_id);
CREATE INDEX IF NOT EXISTS idx_actions_created_at ON actions_taken(created_at DESC);

-- ── leads ─────────────────────────────────────────────────────────────────────
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
    status          TEXT    NOT NULL DEFAULT 'new'
                    CHECK(status IN ('new','contacted','qualified','closed','rejected')),
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── vendors ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vendors (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL,
    company             TEXT    NOT NULL,
    email               TEXT    NOT NULL,
    phone               TEXT,
    brands              TEXT,               -- JSON array: ["Cisco","Meraki"]
    product_categories  TEXT,               -- JSON array: ["networking","security"]
    notes               TEXT,
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── settings ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── imap_sync ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS imap_sync (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_path     TEXT    NOT NULL UNIQUE,
    last_uid        INTEGER NOT NULL DEFAULT 0,
    last_synced_at  TEXT,
    last_count      INTEGER DEFAULT 0
);
