-- Migration 021: agent execution state machine for Create Task in ERP.
--
-- suggested_tasks stays a staging/scratchpad layer. This migration adds the
-- crash-safe execution-state columns needed to push ONE approved create_task
-- proposal to the ERP exactly once, with an atomic claim and attempt fencing.
-- It does NOT call ERP, touch email records, delete or merge rows.
--
-- The whole file runs as one transaction (BEGIN/COMMIT). The migration runner
-- (backend/database/connection.py) executes it with executescript() and only
-- records the filename in _migrations after the script returns, so if any
-- statement here fails the transaction is rolled back on connection close and
-- NO partial 021 objects remain.

BEGIN;

-- --- Precondition: migration 019 must already be applied ---------------------
-- This zero-row SELECT references the four columns migration 019 adds. If any
-- is missing SQLite raises "no such column" and the whole migration aborts and
-- rolls back BEFORE any 021 DDL runs. Do not remove.
SELECT erp_reference, error_message, confidence, evidence_quote
FROM suggested_tasks LIMIT 0;

-- --- New execution-state columns ---------------------------------------------
ALTER TABLE suggested_tasks ADD COLUMN agent_suggestion_key TEXT;

ALTER TABLE suggested_tasks ADD COLUMN execution_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (execution_status IN ('pending', 'executing', 'executed', 'failed'));

ALTER TABLE suggested_tasks ADD COLUMN execution_claimed_at TEXT;   -- UTC claim time
ALTER TABLE suggested_tasks ADD COLUMN execution_attempt_id TEXT;   -- current worker's fence

-- --- Backfill a stable opaque UUIDv4-formatted key for every existing row -----
-- Built from randomblob(16) with the version ("4") and variant ("8/9/a/b")
-- nibbles fixed so the value is a valid UUIDv4 string. New rows get their key
-- from Python uuid.uuid4() at insert time (see the repository create()).
UPDATE suggested_tasks
SET agent_suggestion_key = lower(
        hex(randomblob(4)) || '-' ||
        hex(randomblob(2)) || '-4' ||
        substr(hex(randomblob(2)), 2) || '-' ||
        substr('89ab', (abs(random()) % 4) + 1, 1) ||
        substr(hex(randomblob(2)), 2) || '-' ||
        hex(randomblob(6))
    )
WHERE agent_suggestion_key IS NULL;

-- Rows already executed before this migration are terminal.
UPDATE suggested_tasks SET execution_status = 'executed'
WHERE executed_at IS NOT NULL;

-- --- Uniqueness for non-null keys (partial unique index) ----------------------
CREATE UNIQUE INDEX IF NOT EXISTS idx_suggested_tasks_agent_key
ON suggested_tasks (agent_suggestion_key)
WHERE agent_suggestion_key IS NOT NULL;

COMMIT;
