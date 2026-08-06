# Conversation recall (capability `chat_history`) — design

Date: 2026-08-06. Status: approved by Jordan (agents, visibility, tool shape,
and search mechanism all picked from lettered options).

## Problem

Conversations rotate after 30 minutes idle (`db/conversations.py`): the session
archives and the agent starts fresh. Archived transcripts persist in the
`messages`/`conversations` tables but no agent can reach them. Jordan wants
agents to recall previous chats from the last 30 days.

## Decisions (locked)

- **Who**: all three agents (`claw-main`, `workout-coach`, `med-check`).
- **Visibility**: own chats only. Each agent reads only conversations whose
  `channel_thread_id` is its own slug. No cross-agent recall; med-check health
  conversations never surface in claw-main.
- **Shape**: a search + read pair mirroring `search_notes`/`read_note`.
- **Mechanism**: Postgres ILIKE keyword search. No embeddings, no new tables,
  no schema migration. Semantic search is a later phase only if keyword recall
  proves too blunt.
- **Window**: 30 days, enforced server-side regardless of tool arguments.
- **Archived only**: the active conversation is already in context; recall
  tools never return it. This also keeps the rotation invariant clean — the
  feature adds no per-conversation state.

## Tools

New module `src/jordan_claw/tools/history.py`, capability id `chat_history`.

### `search_past_conversations(query, from_date?, to_date?)`

- ILIKE over `messages.content` (user/assistant roles only), joined via
  PostgREST `!inner` to `conversations` filtered on `org_id`, `channel='app'`,
  `channel_thread_id = <agent slug>`, `status='archived'`, and
  `created_at >= now - 30d` (the hard cap; caller-supplied dates narrow it,
  never widen it).
- Requires a non-empty query OR at least one date bound — never both empty, so
  the model cannot dump 30 days blind.
- Returns at most 10 hits, newest first: excerpt (~150 chars either side of
  the match), role, timestamp, conversation id. Date-only searches return the
  first user message of each matching conversation as the excerpt.
- Docstring boundary: past chat transcripts with Jordan only. NOT for durable
  facts about Jordan (`recall_memory`), his notes (`search_notes`), or the web
  (`search_web`).

### `read_past_conversation(conversation_id, page=1)`

- Pages one archived transcript ~30 messages per page, each message truncated
  to ~500 chars, with a "page X of Y (N messages)" header.
- Ownership enforced in the query (org + slug + archived + 30-day window);
  a wrong or foreign id returns a friendly not-found string.

Both tools hard-cap result count and excerpt length: oversized tool returns
have stranded runs mid-exchange before (Anthropic 400, fixed bf209b7).

## Wiring

- `AgentDeps` gains `agent_slug: str = ""` (defaulted). Plumbed at the three
  construction sites: `gateway/router.py`, `proactive/executors.py`,
  `events/pipeline.py`.
- DB helpers live in `db/messages.py` (search) and reuse/extend the existing
  conversation read paths; `.limit(N).execute()` patterns, never
  `maybe_single()`.
- `agents/capabilities.py`: new `ToolGroup` registry entry with a real
  description — the classifier's agent catalog renders capability
  descriptions, and a description-less entry broke it once.

## Migration

`037_chat_history_grant.sql`, data-only, idempotent:

```sql
UPDATE agents SET capabilities = array_append(capabilities, 'chat_history')
WHERE slug IN ('claw-main', 'workout-coach', 'med-check')
  AND NOT ('chat_history' = ANY(capabilities));
```

Applied by hand after the code deploys (`resolve_capabilities` skips unknown
ids, so either order is safe; code-first is the clean path). No `pg_notify`
needed — data-only.

## Error handling

- Empty query and no date bounds → instructive error string telling the model
  to supply one.
- Unknown/foreign/active conversation id → "No archived conversation with that
  id in your last 30 days."
- Supabase errors follow the existing tool pattern (caught, returned as an
  error string, never an unhandled raise mid-run).

## Testing

- Unit tests: both tools against a mocked supabase boundary (scoping filters,
  30-day clamp, excerpt truncation, pagination math, not-found paths).
- Wiring proof: `TestModel(call_tools=[])` + `last_model_request_parameters`
  asserting both tool definitions reach the model for an agent granted
  `chat_history` (pattern in `tests/test_capabilities.py`).
- Count bumps: N-tools assertion in `tests/test_capabilities.py` and
  `EXPECTED_TOOLS` in `tests/test_tool_registry.py` (37 → 39).

## Verification before done

1. `SELECT slug, capabilities FROM agents` readback shows the grant on all
   three rows.
2. A real prod message ("what did we talk about yesterday?") exercises the
   tool end-to-end; confirm the run in Logfire/usage_events.

## Out of scope

Embeddings/semantic search, cross-agent recall, recall of proactive artifacts
(`proactive_messages` is a separate surface), any Flutter UI change.
