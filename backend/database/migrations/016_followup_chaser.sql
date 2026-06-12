-- Phase 3.1: Follow-up chaser settings
INSERT OR IGNORE INTO settings (key, value, description)
VALUES
  ('followup_threshold_days', '4',  'Days of silence before a follow-up draft is created'),
  ('followup_enabled',        '1',  'Enable the daily follow-up chaser (1=on, 0=off)');
