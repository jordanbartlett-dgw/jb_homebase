-- Drop the legacy per-agent tools array. Tool selection is capability-driven
-- since migration 012; the column has been inert since PR #9.
-- ROLLOUT: run this in the Supabase SQL editor ONLY AFTER the code that stops
-- selecting the column is deployed (dropping first breaks the agents select).
ALTER TABLE agents DROP COLUMN IF EXISTS tools;

NOTIFY pgrst, 'reload schema';
