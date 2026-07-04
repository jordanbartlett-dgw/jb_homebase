-- claude-sonnet-4-20250514 retired 2026-06-15 (API returns 404).
-- Move all agents to the documented replacement.
UPDATE agents
SET model = 'claude-sonnet-5'
WHERE model = 'claude-sonnet-4-20250514';
