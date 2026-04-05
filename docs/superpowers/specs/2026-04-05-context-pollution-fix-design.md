# Context Pollution Fix — Design Spec

**Date:** 2026-04-05
**Status:** Draft
**Problem:** Jordan Claw agent loses intent on multi-turn conversations, defaulting to Obsidian search instead of web search and eventually producing incoherent responses.

## Root Cause

Two structural issues compound:

1. **Weak tool-routing signals.** Tool docstrings don't distinguish internal (Jordan's data) from external (the world). The LLM picks `search_notes` for queries like "find content creators similar to Dan Koe" because the docstring says "by concept or keyword" — which matches everything.

2. **Unbounded conversation history.** `get_recent_messages()` loads up to 50 messages with no token budget. After a few tool-heavy turns, the context window fills with Obsidian note content. This biases subsequent tool selection toward notes and eventually saturates the window, causing incoherent responses (e.g., a weather summary when asked about content creators).

## Changes

### 1. Tool Docstring Routing

Update docstrings so the LLM has clear signals about when to use each tool. The docstring is the primary routing mechanism — it's what the model reads when selecting tools.

**`search_notes`** (obsidian.py):
```
Search Jordan's personal Obsidian notes and saved research.
Only use when Jordan asks about his own notes, past research, or previously saved content.
Do NOT use this to discover new people, companies, content, or external information.
Use read_note to get the full content of a specific result.
```

**`read_note`** (obsidian.py):
```
Read the full content of an Obsidian note by title.
Only use after search_notes returns a relevant result.
Returns the complete note body, tags, and linked notes.
```

**`search_web`** (web_search.py):
```
Search the web for information from the outside world.
Use for discovering new people, companies, content creators, products,
recommendations, current events, comparisons, or anything not already
in Jordan's notes or memory. Default to this tool when unsure whether
information is in Jordan's notes or on the web.
```

All other tools (`recall_memory`, `forget_memory`, `check_calendar`, `schedule_event`, `current_datetime`, `create_source_note`, `fetch_article`) keep their current docstrings — they're already scoped well.

### 2. Token-Budgeted Conversation History

Add a token budget to `db_messages_to_history()` in `factory.py`.

**Algorithm:**
1. Accept a `max_tokens` parameter (default 4000, ~16000 chars at 4 chars/token).
2. Walk the message list from newest to oldest.
3. Estimate each message's token count as `len(content) // 4`.
4. Accumulate messages until the budget is exhausted.
5. Reverse to restore chronological order.
6. Always include at least the most recent message pair (user + assistant) regardless of budget.

**Why 4000 tokens:** The system prompt + memory context is ~1000-1500 tokens. The current user message is ~50-200 tokens. A 4000-token history budget keeps the total prompt under ~6000 tokens, leaving ample room for tool results and the model's response within a typical 8k-16k effective window.

**Where:** Modify `db_messages_to_history()` in `jordan-claw/src/jordan_claw/agents/factory.py`. The function already filters to user/assistant roles. Add budget enforcement after filtering.

### 3. System Prompt Routing Block

Add a tool-routing taxonomy to the agent's system prompt in the Supabase `agents` table. This is a one-time SQL update, not a code change.

```sql
-- Prepend to existing system_prompt for the jordan-assistant agent
UPDATE agents
SET system_prompt = E'## Tool Routing\nYour tools are either *internal* (notes, memory, calendar — Jordan''s own data) or *external* (web search — the outside world). Use internal tools only when Jordan asks about his own notes, saved content, or schedule. For discovering new people, companies, trends, recommendations, or any new information, use search_web. When in doubt, default to search_web.\n\n' || system_prompt
WHERE slug = 'jordan-assistant';
```

## Out of Scope

- **Intent classification step:** Not needed until 10+ tools compete for selection.
- **History summarization:** Token budget truncation is sufficient. Revisit if conversations regularly need deep history.
- **Memory injection changes:** Already capped at 500 tokens, working correctly.
- **Retrieval relevance thresholds:** `search_notes` uses pgvector cosine similarity but has no minimum threshold. Could add later, but fixing tool selection is the higher-leverage fix.

## Files Changed

| File | Change |
|------|--------|
| `jordan-claw/src/jordan_claw/tools/obsidian.py` | Update `search_notes` and `read_note` docstrings |
| `jordan-claw/src/jordan_claw/tools/web_search.py` | Update `search_web` docstring |
| `jordan-claw/src/jordan_claw/agents/factory.py` | Add token budget to `db_messages_to_history()` |
| Supabase `agents` table | One-time SQL update to system prompt |

## Testing

- Unit test: `db_messages_to_history()` with messages exceeding budget truncates oldest first.
- Unit test: budget always preserves at least the most recent exchange.
- Manual test: ask "find content creators similar to Dan Koe" — should call `search_web`, not `search_notes`.
- Manual test: multi-turn conversation with tool-heavy responses stays coherent past turn 5.
