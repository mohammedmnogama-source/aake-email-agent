INSERT OR IGNORE INTO settings (key, value, description) VALUES
    ('gemini_model',       'gemini-2.0-flash', 'Gemini model for email analysis'),
    ('poll_interval_min',  '15',               'IMAP poll frequency in minutes'),
    ('max_few_shot',       '20',               'Max prior decisions included in Gemini prompt'),
    ('target_folder',      'AI Agent',         'IMAP folder name to monitor (exact server path set by setup.py)'),
    ('drafts_folder',      'Drafts',           'IMAP Drafts folder path (exact server path set by setup.py)'),
    ('dashboard_password', '',                 'bcrypt hash of dashboard password — set by setup.py'),
    ('scheduler_status',   'stopped',          'Current scheduler state: running | idle | error | stopped'),
    ('imap_host',          'mail.aqeeqkw.com', 'IMAP server hostname'),
    ('smtp_host',          'mail.aqeeqkw.com', 'SMTP server hostname');
