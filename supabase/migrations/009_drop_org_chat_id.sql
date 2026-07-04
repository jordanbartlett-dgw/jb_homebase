-- Post-deploy cleanup: chat ids now live on agents (008 + code deploy)
-- Apply ONLY after the code deploy is verified (rollout step 6).
ALTER TABLE organizations DROP COLUMN IF EXISTS telegram_chat_id;

SELECT pg_notify('pgrst', 'reload schema');
