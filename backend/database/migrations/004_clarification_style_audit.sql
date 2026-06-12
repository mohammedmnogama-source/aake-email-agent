-- Migration 004: Clarification, Style Learning, Audit Log, Test Mode

-- ── emails table: rebuild with expanded status CHECK constraint ───────────────
-- SQLite cannot ALTER a CHECK constraint, so we recreate the table.
PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS emails_new (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    imap_uid        INTEGER NOT NULL,
    folder_path     TEXT    NOT NULL,
    subject         TEXT,
    from_address    TEXT    NOT NULL,
    from_name       TEXT,
    to_addresses    TEXT    NOT NULL,
    cc_addresses    TEXT,
    body_text       TEXT,
    body_preview    TEXT,
    received_at     TEXT    NOT NULL,
    fetched_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    has_attachments INTEGER NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK(status IN (
                        'pending','processing','decided','parse_error','error',
                        'clarification_pending','skipped','manually_handled'
                    )),
    UNIQUE(imap_uid, folder_path)
);

INSERT INTO emails_new SELECT
    id, imap_uid, folder_path, subject, from_address, from_name,
    to_addresses, cc_addresses, body_text, body_preview, received_at,
    fetched_at, has_attachments, status
FROM emails;

DROP TABLE emails;
ALTER TABLE emails_new RENAME TO emails;

CREATE INDEX IF NOT EXISTS idx_emails_status      ON emails(status);
CREATE INDEX IF NOT EXISTS idx_emails_received_at ON emails(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_emails_from        ON emails(from_address);

PRAGMA foreign_keys = ON;

-- ── ai_suggestions additions ──────────────────────────────────────────────────
-- Columns already included in 000_baseline_rebuilt.sql — no ALTER needed on fresh DB.

-- ── clarification_responses ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clarification_responses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    suggestion_id INTEGER NOT NULL REFERENCES ai_suggestions(id) ON DELETE CASCADE,
    email_id      INTEGER NOT NULL REFERENCES emails(id),
    round         INTEGER NOT NULL DEFAULT 1,   -- max 3
    mo_answer     TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── writing_style ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS writing_style (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_json TEXT    NOT NULL,
    email_count  INTEGER NOT NULL,
    confirmed    INTEGER NOT NULL DEFAULT 0,  -- 1 = Mo confirmed dry-run
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── style_examples (redacted bodies only) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS style_examples (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject      TEXT,
    body_preview TEXT,
    body_full    TEXT    NOT NULL,   -- redacted version only, never original
    context_type TEXT,               -- 'reply_to_lead'|'reply_to_vendor'|'inquiry'|'other'
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ── api_audit_log ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_audit_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT    NOT NULL DEFAULT (datetime('now')),
    model            TEXT    NOT NULL,
    purpose          TEXT    NOT NULL,  -- 'email_analysis'|'style_extraction'|'clarification_rerun'
    prompt_size      INTEGER NOT NULL,  -- character count
    response_size    INTEGER NOT NULL,
    prompt_hash      TEXT    NOT NULL,  -- sha256 of prompt (not stored, just hash)
    redactions_count INTEGER NOT NULL DEFAULT 0,
    email_id         INTEGER REFERENCES emails(id)
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON api_audit_log(timestamp DESC);

-- ── manually_handled_patterns ─────────────────────────────────────────────────
-- Future emails from same domain+category auto-suggest 'manually_handled'
CREATE TABLE IF NOT EXISTS manually_handled_patterns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    from_domain   TEXT    NOT NULL,
    category      TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(from_domain, category)
);

-- ── settings additions ────────────────────────────────────────────────────────
INSERT OR IGNORE INTO settings (key, value, description) VALUES
    ('use_style_for_drafts', '1',  'Include writing style in draft prompts (1=on, 0=off)'),
    ('style_last_updated',   '',   'ISO timestamp of last style refresh'),
    ('style_email_count',    '0',  'Number of sent emails analyzed for style'),
    ('style_confirmed',      '0',  'Whether Mo confirmed the dry-run style profile'),
    ('test_mode',            '1',  'When 1: approve writes to file not webmail Drafts');
