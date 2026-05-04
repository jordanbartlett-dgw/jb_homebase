-- 006_usage_events.sql
-- One row per agent run. Source of truth for cost / latency / outcome analytics.
-- agent_slug is denormalized text (no FK) so synthetic slugs like
-- 'memory-extractor' work even though they're not in the agents table.
-- channel accepts synthetic values: telegram, proactive, memory_extract,
-- and future client values (flutter, web). One column, no separate `source`.

create table usage_events (
    id              uuid primary key default gen_random_uuid(),
    created_at      timestamptz not null default now(),
    org_id          uuid references organizations(id),
    agent_slug      text not null,
    conversation_id uuid references conversations(id) on delete set null,
    channel         text not null,
    run_kind        text not null check (run_kind in
                        ('user_message','proactive','memory_extract','eval')),
    schedule_name   text,
    model           text,
    input_tokens    int,
    output_tokens   int,
    cost_usd        numeric(10, 6),
    duration_ms     int,
    tool_call_count int not null default 0,
    success         boolean not null,
    error_type      text,
    error_severity  text check (error_severity in
                        ('low','medium','high','critical')),
    metadata        jsonb default '{}'
);

create index idx_usage_events_agent_created  on usage_events(agent_slug, created_at desc);
create index idx_usage_events_org_created    on usage_events(org_id, created_at desc);
create index idx_usage_events_kind_created   on usage_events(run_kind, created_at desc);
create index idx_usage_events_conversation   on usage_events(conversation_id) where conversation_id is not null;

alter table usage_events enable row level security;

-- Retention: not enforced. At single-user volume (~50 events/day), the table
-- will reach 100k rows in ~5 years. When count exceeds 1M or query latency
-- on indexed reads exceeds 100ms, add a pg_cron job:
--   delete from usage_events where created_at < now() - interval '18 months';
-- Same convention applies to feedback (007) and any future analytics tables.

select pg_notify('pgrst', 'reload schema');
