-- Weekly care-document staleness check (phase 3). DATA migration.
-- Deploy order: run AFTER the phase-3 deploy (executor must exist) — an
-- unknown task_type never gets its last_run_at updated, so a pre-deploy row
-- would warn every scheduler tick.
-- Idempotent via the (org_id, name) unique constraint.

INSERT INTO proactive_schedules (org_id, name, cron_expression, timezone, task_type, config)
VALUES (
    '1408252a-fd36-4fd3-b527-3b2f495d7b9c',
    'care_docs_check',
    '0 17 * * 0',
    'America/Chicago',
    'care_docs_check',
    '{"agent_slug": "med-check"}'
)
ON CONFLICT (org_id, name) DO NOTHING;

-- Verify:
-- SELECT name, cron_expression, timezone, enabled FROM proactive_schedules
-- WHERE name = 'care_docs_check';
