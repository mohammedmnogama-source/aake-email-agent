-- Migration 019: staging columns for suggested_tasks
-- suggested_tasks stays a staging/scratchpad layer only — ERP/Supabase remains
-- the system of record. These 4 nullable columns let a row hold the outcome of
-- a human-approved ERP action plus the AI's trust signals. No new tables.

ALTER TABLE suggested_tasks ADD COLUMN erp_reference  TEXT;  -- ERP-returned id/reference after approval
ALTER TABLE suggested_tasks ADD COLUMN error_message  TEXT;  -- populated if the ERP call failed
ALTER TABLE suggested_tasks ADD COLUMN confidence     REAL;  -- AI confidence 0-1
ALTER TABLE suggested_tasks ADD COLUMN evidence_quote TEXT;  -- snippet from the email justifying the action
