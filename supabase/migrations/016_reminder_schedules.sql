-- One-shot + reminder support on proactive_schedules (Phase 1, Task 3).
-- Deploy order: run BEFORE merging the code that reads run_at/source. Columns
-- are additive and the current code ignores them. Do NOT hand-create rows with
-- a null cron_expression until the new code is live — the old ProactiveSchedule
-- model requires cron and a null would fail validation for ALL schedules.
--
-- run_at: one-shot fire time (fires once; dispatch flips enabled=false after).
-- source: 'system' = operator-seeded jobs, 'reminder' = created by the
--         set_reminder tool. list_reminders only ever shows source='reminder'.

ALTER TABLE proactive_schedules ALTER COLUMN cron_expression DROP NOT NULL;
ALTER TABLE proactive_schedules ADD COLUMN IF NOT EXISTS run_at timestamptz;
ALTER TABLE proactive_schedules ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'system';

ALTER TABLE proactive_schedules DROP CONSTRAINT IF EXISTS proactive_schedules_timing_check;
ALTER TABLE proactive_schedules ADD CONSTRAINT proactive_schedules_timing_check
    CHECK (cron_expression IS NOT NULL OR run_at IS NOT NULL);

SELECT pg_notify('pgrst', 'reload schema');

-- Verify:
-- SELECT column_name, is_nullable FROM information_schema.columns
-- WHERE table_name = 'proactive_schedules' AND column_name IN ('cron_expression','run_at','source');
