-- 018_thread_summary.sql
-- Stores the whole-thread briefing (CONTEXT / SUMMARY / STATUS / NEXT STEPS)
-- generated automatically at sync time. NULL for emails synced before this feature
-- (the ERP shows a "Summarize thread" button for those).
ALTER TABLE ai_suggestions ADD COLUMN thread_summary TEXT;
