-- Add direct IMAP tracking columns so price extraction works without the emails table
ALTER TABLE price_quotes ADD COLUMN imap_uid    INTEGER;
ALTER TABLE price_quotes ADD COLUMN folder_path TEXT;
ALTER TABLE price_quotes ADD COLUMN email_subject TEXT;
ALTER TABLE price_quotes ADD COLUMN email_from   TEXT;

CREATE INDEX IF NOT EXISTS idx_price_quotes_uid_folder ON price_quotes(imap_uid, folder_path);
