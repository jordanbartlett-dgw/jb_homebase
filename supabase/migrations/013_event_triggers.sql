-- 013_event_triggers.sql
-- Event-driven triggers: inbound events (webhooks, watchers) fan out to
-- agent runs via event_triggers rows. watcher_cursors tracks poll position
-- for pull-based sources (Fastmail JMAP).

CREATE TABLE IF NOT EXISTS event_triggers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid REFERENCES organizations(id),
    source text NOT NULL,
    name text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    agent_slug text NOT NULL,
    prompt_template text NOT NULL,
    filter jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_event_triggers_source ON event_triggers(source) WHERE enabled;

CREATE TABLE IF NOT EXISTS watcher_cursors (
    source text PRIMARY KEY,
    cursor jsonb NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- run_kind gains 'event' and 'voice' (checked constraint, see 006).
-- NOTE: the DROP below assumes Postgres auto-named the constraint
-- usage_events_run_kind_check. Verify at apply time with:
--   select conname from pg_constraint
--   where conrelid = 'usage_events'::regclass and contype = 'c';
-- and adjust the name if it differs.
ALTER TABLE usage_events DROP CONSTRAINT usage_events_run_kind_check;
ALTER TABLE usage_events ADD CONSTRAINT usage_events_run_kind_check
    CHECK (run_kind IN ('user_message','proactive','memory_extract','eval','event','voice'));

-- Proof trigger: notable inbound email -> claw-main summary
INSERT INTO event_triggers (org_id, source, name, agent_slug, prompt_template)
VALUES (
    '1408252a-fd36-4fd3-b527-3b2f495d7b9c',
    'fastmail-email',
    'inbound_email_review',
    'claw-main',
    'New email received. From: {from}. Subject: {subject}. Preview: {snippet}. If this needs Jordan''s attention, summarize it in one or two sentences and say why it matters. If it is routine or automated noise, reply with exactly NOTHING_TO_SEND.'
);

-- Fastmail watcher schedule: poll JMAP every 5 minutes
INSERT INTO proactive_schedules (org_id, name, cron_expression, timezone, task_type, config)
VALUES
    ('1408252a-fd36-4fd3-b527-3b2f495d7b9c', 'fastmail_watch', '*/5 * * * *', 'America/Chicago', 'fastmail_watch', '{}')
ON CONFLICT (org_id, name) DO NOTHING;

-- Notify PostgREST to pick up new tables
SELECT pg_notify('pgrst', 'reload schema');
