-- 007_feedback.sql
-- Personal outcome signals: how Jordan rated each agent over time.
-- prompt_source distinguishes ad-hoc /feedback from the weekly review prompt
-- so we can analyze response rates and rating distributions per source.

create table feedback (
    id              uuid primary key default gen_random_uuid(),
    created_at      timestamptz not null default now(),
    org_id          uuid references organizations(id),
    agent_slug      text not null,
    conversation_id uuid references conversations(id) on delete set null,
    rating          int not null check (rating between 1 and 5),
    note            text,
    prompt_source   text not null check (prompt_source in ('manual','weekly_review')),
    metadata        jsonb default '{}'
);

create index idx_feedback_agent_created on feedback(agent_slug, created_at desc);
create index idx_feedback_org_created   on feedback(org_id, created_at desc);

alter table feedback enable row level security;

-- Retention: not enforced (see usage_events 006 for the policy + trigger condition).
-- Apply the same pg_cron pattern when row count or query latency thresholds trip.

-- Seed the weekly feedback request schedule (Sunday 7pm Central).
insert into proactive_schedules (org_id, name, cron_expression, timezone, task_type, config)
values
    (
        '1408252a-fd36-4fd3-b527-3b2f495d7b9c',
        'weekly_feedback_request',
        '0 19 * * 0',
        'America/Chicago',
        'weekly_feedback_request',
        '{"agent_slug": "claw-main"}'
    )
on conflict (org_id, name) do nothing;

select pg_notify('pgrst', 'reload schema');
