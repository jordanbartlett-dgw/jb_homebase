-- 033_cost_coverage.sql
-- Deploy order: run BEFORE merging the feat/cost-coverage branch.
-- Adds prompt-cache token columns and two run kinds: 'classifier'
-- (voice routing haiku calls) and 'transcription' (Whisper).

alter table usage_events add column if not exists cache_read_tokens int;
alter table usage_events add column if not exists cache_write_tokens int;

-- NOTE: verify the auto-generated constraint name at apply time (see 013):
--   select conname from pg_constraint
--   where conrelid = 'usage_events'::regclass and contype = 'c';
ALTER TABLE usage_events DROP CONSTRAINT usage_events_run_kind_check;
ALTER TABLE usage_events ADD CONSTRAINT usage_events_run_kind_check
    CHECK (run_kind IN ('user_message','proactive','memory_extract','eval',
                        'event','voice','classifier','transcription'));

select pg_notify('pgrst', 'reload schema');
