-- 037_chat_history_grant.sql
-- Grants the chat_history capability (search_past_conversations,
-- read_past_conversation) to all three agents. Own-thread archived
-- conversations only; 30-day window enforced in code.
--
-- Deploy order: data-only, apply AFTER the chat_history code deploy is
-- live (resolve_capabilities skips unknown ids, so early apply is safe
-- too). No pg_notify needed (no schema change). Idempotent.

UPDATE agents
SET capabilities = array_append(capabilities, 'chat_history')
WHERE slug IN ('claw-main', 'workout-coach', 'med-check')
  AND NOT ('chat_history' = ANY(capabilities));
