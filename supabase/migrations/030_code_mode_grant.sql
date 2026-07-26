-- 030_code_mode_grant.sql
-- Data-only. Deploy order: run AFTER the code deploy that registers the
-- code_mode capability (unknown ids are skipped, but the grant is inert
-- until the code ships). No apostrophes: safe to paste in the SQL Editor.
-- Rollback: UPDATE agents SET capabilities = array_remove(capabilities,
-- 'code_mode') WHERE slug = 'claw-main';

UPDATE agents SET capabilities = array_append(capabilities, 'code_mode')
WHERE slug = 'claw-main' AND NOT ('code_mode' = ANY(capabilities));

-- Verify:
-- SELECT slug, capabilities FROM agents WHERE slug = 'claw-main';
