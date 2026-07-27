-- 034_online_eval_grant.sql
-- Data-only. Deploy order: apply BEFORE merging the branch that registers the
-- online_eval / online_eval_deterministic capabilities (unknown ids are
-- skipped, but the grant is inert until the code ships). No apostrophes:
-- safe to paste in the SQL Editor.
-- claw-main gets the judge-bearing online_eval (its content already exports
-- to Logfire). med-check gets the judge-free online_eval_deterministic:
-- the locked PII decision keeps med-check content out of Logfire, and the
-- groundedness judge (include_input=True, its own instrumented agent) would
-- export that content if sampled. Judge-sampling med-check would require an
-- explicit content-privacy decision first.
-- NULL-safe guard: capabilities can be null on a row, and 'x' = any(null)
-- evaluates to null rather than false, so coalesce it before negating.
-- Rollback:
-- UPDATE agents SET capabilities = array_remove(capabilities, 'online_eval')
--   WHERE slug = 'claw-main';
-- UPDATE agents SET capabilities = array_remove(capabilities, 'online_eval_deterministic')
--   WHERE slug = 'med-check';

update agents
set capabilities = array_append(capabilities, 'online_eval')
where slug = 'claw-main'
  and not coalesce('online_eval' = any(capabilities), false);

update agents
set capabilities = array_append(capabilities, 'online_eval_deterministic')
where slug = 'med-check'
  and not coalesce('online_eval_deterministic' = any(capabilities), false);

select pg_notify('pgrst', 'reload schema');

-- Verify:
-- SELECT slug, capabilities FROM agents WHERE slug IN ('claw-main', 'med-check');
