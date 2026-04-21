-- Prepend tool-routing taxonomy to the agent system prompt.
-- Guard prevents double-prepending if run twice.
UPDATE agents
SET system_prompt = E'## Tool Routing\nYour tools are either *internal* (notes, memory, calendar — Jordan''s own data) or *external* (web search — the outside world). Use internal tools only when Jordan asks about his own notes, saved content, or schedule. For discovering new people, companies, trends, recommendations, or any new information, use search_web. When in doubt, default to search_web.\n\n' || system_prompt
WHERE slug = 'jordan-assistant'
  AND system_prompt NOT LIKE '%Tool Routing%';
