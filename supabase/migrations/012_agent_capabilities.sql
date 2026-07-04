-- Capability bundles replace per-tool filtering (pydantic-ai v2 architecture).
-- Additive: old code ignores this column, so apply to prod before the deploy.
ALTER TABLE agents ADD COLUMN IF NOT EXISTS capabilities text[] NOT NULL DEFAULT '{}';

UPDATE agents SET capabilities = ARRAY['core','web','calendar','memory','obsidian']
WHERE slug = 'claw-main';

UPDATE agents SET capabilities = ARRAY['core','calendar','memory','workout']
WHERE slug = 'workout-coach';

-- The tools column stays until this deploy is verified, then drops in a
-- follow-up migration. Do not write to it after this point.
