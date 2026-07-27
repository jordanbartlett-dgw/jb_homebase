-- 034_online_eval_grant.sql
-- Data-only. Deploy order: apply BEFORE merging the branch that registers the
-- online_eval capability (unknown ids are skipped, but the grant is inert
-- until the code ships). No apostrophes: safe to paste in the SQL Editor.
-- NULL-safe guard: capabilities can be null on a row, and 'x' = any(null)
-- evaluates to null rather than false, so coalesce it before negating.
-- Rollback: UPDATE agents SET capabilities = array_remove(capabilities,
-- 'online_eval') WHERE slug IN ('claw-main', 'med-check');

update agents
set capabilities = array_append(capabilities, 'online_eval')
where slug in ('claw-main', 'med-check')
  and not coalesce('online_eval' = any(capabilities), false);

select pg_notify('pgrst', 'reload schema');

-- Verify:
-- SELECT slug, capabilities FROM agents WHERE slug IN ('claw-main', 'med-check');
