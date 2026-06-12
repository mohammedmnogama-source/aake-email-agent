CREATE TABLE IF NOT EXISTS contacts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    email        TEXT    NOT NULL UNIQUE,
    display_name TEXT,
    frequency    INTEGER NOT NULL DEFAULT 1,
    last_seen    TEXT    NOT NULL DEFAULT (datetime('now')),
    source       TEXT    -- 'from' | 'to' | 'cc' | 'vendor'
);

CREATE INDEX IF NOT EXISTS idx_contacts_email     ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_contacts_frequency ON contacts(frequency DESC);
