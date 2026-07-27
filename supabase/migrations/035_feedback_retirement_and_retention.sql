-- 035_feedback_retirement_and_retention.sql
-- Deploy order: run BEFORE merging the chore/alerts-and-docs branch that
-- deletes db/feedback.py, most_recent_agent, and feedback_submitted.
--
-- Part 1: retire the orphaned feedback surface. The 007-era path
-- (/feedback bot command -> feedback table -> most_recent_agent ->
-- feedback_submitted PostHog event) has zero production callers: the
-- /feedback command is long deleted, and phase 3's trace-attached feedback
-- (POST /app/feedback, see docs/observability.md "Feedback") supersedes it.
--
-- Part 1b: the weekly_feedback_request proactive schedule (seeded in 007)
-- sends a chat prompt telling the user to reply with the now-deleted
-- `/feedback weekly <1-5>` command. Its backing (feedback table,
-- most_recent_agent, the /feedback command itself) is gone, so the prompt
-- asks for input that goes nowhere. DISABLE, do not delete: historical
-- proactive_messages rows hold FK references to this schedule id
-- (proactive_messages_schedule_id_fkey), so a delete fails with 23503.
-- A disabled row is inert (the scheduler only reads enabled = true) and
-- the update is idempotent.
--
-- Part 2: usage_events retention via pg_cron. NOTE: pg_cron may not be
-- available on every Supabase plan/tier. If `create extension` below fails
-- or is unavailable, skip the cron.schedule block entirely and instead run
-- the delete statement by hand on a recurring basis (documented in
-- docs/observability.md as a manual runbook line):
--   delete from usage_events where created_at < now() - interval '180 days';

drop table if exists feedback;

update proactive_schedules set enabled = false
where task_type = 'weekly_feedback_request';

create extension if not exists pg_cron;

do $$ begin
  if not exists (select 1 from cron.job where jobname = 'usage-events-retention') then
    perform cron.schedule(
      'usage-events-retention',
      '30 4 * * *',
      $job$delete from usage_events where created_at < now() - interval '180 days'$job$
    );
  end if;
end $$;

select pg_notify('pgrst', 'reload schema');

-- Verify:
-- SELECT jobname, schedule, command FROM cron.job WHERE jobname = 'usage-events-retention';
-- SELECT to_regclass('public.feedback'); -- should be NULL
-- SELECT enabled FROM proactive_schedules WHERE task_type = 'weekly_feedback_request'; -- false (or no rows)
