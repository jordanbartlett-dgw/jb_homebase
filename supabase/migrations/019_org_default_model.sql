-- Org-level default model + nullable agent override (Phase 1, Task 5) — schema half.
-- Deploy order: run BEFORE merging the code that resolves NULL models.
-- Safe for the currently deployed code: adds a column it ignores and relaxes
-- a constraint on values that all remain set. Do NOT null any agents.model
-- until the resolving code is live — that flip is migration 020.

ALTER TABLE organizations ADD COLUMN IF NOT EXISTS default_model text;

UPDATE organizations SET default_model = 'anthropic:claude-sonnet-5'
WHERE default_model IS NULL;

ALTER TABLE agents ALTER COLUMN model DROP NOT NULL;

SELECT pg_notify('pgrst', 'reload schema');

-- Verify:
-- SELECT id, default_model FROM organizations;
-- SELECT column_name, is_nullable FROM information_schema.columns
-- WHERE table_name = 'agents' AND column_name = 'model';
