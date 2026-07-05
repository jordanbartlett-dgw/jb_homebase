-- pydantic-ai v2 removed bare-model-name provider inference; model strings
-- must carry an explicit provider prefix. Prefix any bare names and fix the
-- column default. Prefixed names are also valid under v1, so this migration
-- MUST be applied to prod BEFORE the v2 code deploys.
UPDATE agents
SET model = 'anthropic:' || model
WHERE model NOT LIKE '%:%'
  AND model <> 'test';

-- 001 set the default to claude-sonnet-4-20250514 (retired 2026-06-15, see
-- 010, which moved rows but not the default). Point it at the current model.
ALTER TABLE agents
  ALTER COLUMN model SET DEFAULT 'anthropic:claude-sonnet-5';
