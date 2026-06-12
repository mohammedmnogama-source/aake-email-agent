-- Add is_read flag to emails so the UI can show unread/read state
ALTER TABLE emails ADD COLUMN is_read INTEGER NOT NULL DEFAULT 0;
