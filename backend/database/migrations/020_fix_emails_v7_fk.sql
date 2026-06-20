-- Migration 020: fix the broken `emails_v7` foreign-key references (error log #1)
--
-- WHY: 000_baseline_rebuilt.sql defines these tables with `REFERENCES emails(id)`,
-- but migration 008 runs `ALTER TABLE emails RENAME TO emails_v7`. SQLite 3.26+
-- silently rewrites every FK in OTHER tables to point at the new name. 008 then
-- recreates `emails` and drops `emails_v7`, leaving 9 tables pointing at a table
-- that no longer exists. On a FRESH-from-migrations DB (e.g. a new Railway volume
-- or a test DB) any INSERT into them fails:
--     no such table: main.emails_v7
-- The REAL production DB (data/agent.db) predates the baseline rebuild and already
-- references `emails` correctly, so this only bites brand-new DBs.
--
-- Affected tables: ai_suggestions, decisions, actions_taken, leads,
-- clarification_responses, suggested_tasks, price_quotes, rfqs, api_audit_log.
--
-- FIX: rewrite only the FK text in the stored schema (emails_v7 -> emails) using
-- writable_schema. This corrects the FK definitions in place WITHOUT rebuilding
-- the tables, so no data is copied or risked. FK enforcement is turned off around
-- the change per error log #1. The UPDATE only touches rows that actually contain
-- `emails_v7`, so on the production DB (already correct) this migration is a no-op.

PRAGMA foreign_keys = OFF;
PRAGMA writable_schema = ON;

UPDATE sqlite_master
SET sql = replace(sql, '"emails_v7"', 'emails')
WHERE type = 'table' AND sql LIKE '%"emails_v7"%';

PRAGMA writable_schema = OFF;
PRAGMA foreign_keys = ON;
