-- Flip both agents to inherit the org default model (Phase 1, Task 5) — data half.
-- Deploy order: run AFTER migration 019 AND after the code deploy that
-- resolves NULL models. The pre-indirection code validates AgentConfig.model
-- as a required string — nulling these rows earlier downs both bots.
-- A future per-agent override is just: UPDATE agents SET model = '...' WHERE slug = '...'.

UPDATE agents SET model = NULL
WHERE slug IN ('claw-main', 'workout-coach') AND model = 'anthropic:claude-sonnet-5';

-- Verify (expect model NULL for both, resolved via organizations.default_model):
-- SELECT slug, model FROM agents WHERE slug IN ('claw-main', 'workout-coach');
-- Then hit /health: both agents must report the resolved model and model_ok=true.
