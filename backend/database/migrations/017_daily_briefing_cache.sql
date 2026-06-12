-- Cache for daily briefing so it survives server restarts
CREATE TABLE IF NOT EXISTS daily_briefing (
    id          INTEGER PRIMARY KEY CHECK (id = 1),  -- single row only
    generated_at TEXT NOT NULL,
    email_count  INTEGER NOT NULL DEFAULT 0,
    overview     TEXT NOT NULL DEFAULT '',
    attention_json TEXT NOT NULL DEFAULT '[]',
    vendors_json   TEXT NOT NULL DEFAULT '[]',
    priorities_json TEXT NOT NULL DEFAULT '[]'
);
