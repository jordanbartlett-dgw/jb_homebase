-- 032_observability_hardening.sql
-- Deploy order: run BEFORE merging the fix/observability-hardening branch.
-- 1) trace_id joins a usage_events row to its Logfire trace (hex trace id).
-- 2) med-check gets the private_content capability (include_content=False
--    instrumentation): its conversations carry a child's medical data and
--    must not export prompt/completion content to Logfire.

alter table usage_events add column if not exists trace_id text;

comment on column usage_events.trace_id is
  'OTel trace id (32-char hex) of the agent_run span, for Logfire cross-reference';

update agents
set capabilities = array_append(capabilities, 'private_content')
where slug = 'med-check'
  and not ('private_content' = any(capabilities));

select pg_notify('pgrst', 'reload schema');
