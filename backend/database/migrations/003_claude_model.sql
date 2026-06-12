-- Rename gemini_model setting to ai_model and update value for Claude
INSERT OR IGNORE INTO settings (key, value, description)
    VALUES ('ai_model', 'claude-haiku-4-5-20251001', 'Claude model for email analysis');

UPDATE settings SET
    value = 'claude-haiku-4-5-20251001',
    description = 'Claude model for email analysis',
    updated_at = datetime('now')
WHERE key = 'ai_model';
