-- Stores every draft Mo approves, including edits he made before approving.
-- This is the "ground truth" for learning Mo's writing style over time.
-- When was_edited = 1, approved_content differs from original_draft — that means
-- Mo changed Claude's suggestion. Future drafts should match approved_content, not original_draft.

CREATE TABLE IF NOT EXISTS approved_drafts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id            INTEGER NOT NULL,           -- which email this approval came from
    email_subject       TEXT,                       -- subject line (for RAG search)
    email_from_name     TEXT,                       -- sender name
    email_from_address  TEXT,                       -- sender email
    email_category      TEXT,                       -- lead / customer_inquiry / etc
    original_draft      TEXT,                       -- what Claude originally wrote
    approved_content    TEXT NOT NULL,              -- what Mo actually approved (may differ)
    was_edited          INTEGER NOT NULL DEFAULT 0, -- 1 if Mo changed the draft before approving
    approved_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
