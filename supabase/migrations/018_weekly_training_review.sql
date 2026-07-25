-- Weekly training review schedule (Phase 1, Task 4).
-- Data-only. Deploy order: run AFTER the code deploy that adds the
-- weekly_training_review executor — an unknown task_type never gets its
-- last_run_at updated, so a pre-deploy row would warn every scheduler tick.
-- Idempotent via the (org_id, name) unique constraint.

INSERT INTO proactive_schedules (org_id, name, cron_expression, timezone, task_type, config)
VALUES (
    '1408252a-fd36-4fd3-b527-3b2f495d7b9c',
    'weekly_training_review',
    '0 18 * * 0',
    'America/Chicago',
    'weekly_training_review',
    '{"agent_slug": "workout-coach"}'
)
ON CONFLICT (org_id, name) DO NOTHING;

-- Verify:
-- SELECT name, cron_expression, timezone, enabled FROM proactive_schedules
-- WHERE name = 'weekly_training_review';
