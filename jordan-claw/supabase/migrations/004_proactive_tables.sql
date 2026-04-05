-- Proactive Messaging tables (Phase 3c)

-- Add telegram_chat_id to orgs for outbound message delivery
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS telegram_chat_id bigint;

-- Scheduled proactive task definitions
CREATE TABLE IF NOT EXISTS proactive_schedules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES orgs(id),
    name text NOT NULL,
    cron_expression text NOT NULL,
    timezone text NOT NULL DEFAULT 'America/Chicago',
    enabled boolean NOT NULL DEFAULT true,
    task_type text NOT NULL,
    config jsonb NOT NULL DEFAULT '{}',
    last_run_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Audit log of proactive messages sent
CREATE TABLE IF NOT EXISTS proactive_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES orgs(id),
    schedule_id uuid REFERENCES proactive_schedules(id),
    task_type text NOT NULL,
    trigger text NOT NULL,
    content text NOT NULL,
    channel text NOT NULL DEFAULT 'telegram',
    delivered_at timestamptz NOT NULL DEFAULT now()
);

-- Index for dedup check: same schedule, same day
CREATE INDEX IF NOT EXISTS idx_proactive_messages_dedup
    ON proactive_messages (schedule_id, delivered_at);

-- Index for schedule lookup
CREATE INDEX IF NOT EXISTS idx_proactive_schedules_enabled
    ON proactive_schedules (org_id, enabled) WHERE enabled = true;

-- Seed schedules for Jordan's org
INSERT INTO proactive_schedules (org_id, name, cron_expression, timezone, task_type, config)
VALUES
    ('1408252a-fd36-4fd3-b527-3b2f495d7b9c', 'morning_briefing', '0 7 * * *', 'America/Chicago', 'morning_briefing', '{"agent_slug": "claw-main"}'),
    ('1408252a-fd36-4fd3-b527-3b2f495d7b9c', 'weekly_review', '0 8 * * 1', 'America/Chicago', 'weekly_review', '{"agent_slug": "claw-main"}'),
    ('1408252a-fd36-4fd3-b527-3b2f495d7b9c', 'daily_scan', '0 7 * * *', 'America/Chicago', 'daily_scan', '{"agent_slug": "claw-main"}')
ON CONFLICT DO NOTHING;

-- Notify PostgREST to pick up new tables
SELECT pg_notify('pgrst', 'reload schema');
