-- Phase 2: category trust tracking table
-- Tracks per-category approval streaks and trust status.
CREATE TABLE IF NOT EXISTS category_trust (
    category        TEXT PRIMARY KEY,
    streak          INTEGER NOT NULL DEFAULT 0,
    trusted         INTEGER NOT NULL DEFAULT 0,
    trusted_at      TEXT,
    total_approved  INTEGER NOT NULL DEFAULT 0,
    total_edited    INTEGER NOT NULL DEFAULT 0
);

-- Seed trust_threshold setting (streak needed to earn trust)
INSERT OR IGNORE INTO settings (key, value, description)
VALUES ('trust_threshold', '10', 'Number of consecutive unedited approvals needed to trust a category');

-- Add auto_finished flag to ai_suggestions
ALTER TABLE ai_suggestions ADD COLUMN auto_finished INTEGER NOT NULL DEFAULT 0;
