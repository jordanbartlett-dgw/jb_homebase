---
name: extending-the-claw
description: Use when adding an agent tool, a capability group, a new agent, or granting an agent new abilities in jb_homebase — any change touching CAPABILITY_REGISTRY, the agents table, tool functions in src/jordan_claw/tools/, or "make the agent able to X" requests.
---

# Extending the Claw (tools, capabilities, agents)

Read `docs/architecture.md` first. Tools are plain async fns; capability groups
bundle them; the `agents.capabilities text[]` DB column grants them. There is no
`tools` column (dropped, migration 014) and no `@agent.tool` decorators.

## Adding a tool — checklist

1. **Reuse first.** If the tool talks to a service we already integrate, extend
   the existing client code (Fastmail JMAP → `events/fastmail.py`, Whisper →
   `gateway/voice.py`, CalDAV → `tools/calendar.py`, Tavily →
   `tools/web_search.py`, embeddings → `obsidian/embeddings.py`). Extract a
   shared helper rather than writing a second client. Duplicated integration
   code is a review-reject here.
2. Write the async fn in `src/jordan_claw/tools/` taking
   `ctx: RunContext[AgentDeps]`. Need a new credential? Add a defaulted field
   to `AgentDeps` and plumb it from `Settings` at every construction site
   (router, telegram dispatcher, main.py, voice.py, events/pipeline.py,
   proactive/executors.py) — grep `AgentDeps(`.
3. **Docstring = routing signal.** The LLM chooses tools by docstring alone.
   State what it's for AND what it's NOT for, e.g. "Search Jordan's Obsidian
   notes. Not for facts about the outside world — use search_web for that."
   A bare summary line fails review (this exact gap caused the
   search_notes/search_web misrouting incident, lesson 8).
4. Register in `agents/capabilities.py`: add to an existing `ToolGroup` or
   create a new registry entry with `_toolset((fn, "tool_name"))`.
5. Tests — three layers, all required:
   - Unit-test the fn's logic (mock the HTTP/DB boundary).
   - **Wiring proof**: `TestModel(call_tools=[])` +
     `last_model_request_parameters` to assert the tool definition reaches the
     model for an agent with that capability, or `FunctionModel` for a
     run-through (patterns in `tests/test_capabilities.py`). Mocked unit tests
     alone have shipped signature-drift bugs.
   - Bump the exact-count assertions: N-tools test in
     `tests/test_capabilities.py` and `EXPECTED_TOOLS` in
     `tests/test_tool_registry.py`.
6. Grant it: data migration (next number, 021+) appending the capability id to
   the agent row's array, idempotent:
   ```sql
   UPDATE agents SET capabilities = array_append(capabilities, 'email')
   WHERE slug = 'claw-main' AND NOT ('email' = ANY(capabilities));
   -- data-only: no pg_notify needed (that's for SCHEMA changes, and only the
   -- SELECT pg_notify('pgrst','reload schema') form works in the SQL Editor)
   ```
   Applied by hand in the Supabase SQL Editor (see supabase-python skill for
   the migration procedure). `resolve_capabilities` skips unknown ids, so
   either deploy order is safe; clean path is code first, then grant.
7. Verify like it's prod (it is): `SELECT slug, capabilities FROM agents...`,
   then a real message that exercises the tool, then check the run in
   Logfire/usage_events.

## Adding an agent — deltas from the above

- Agent = a new `agents` row (org_id, slug, system_prompt, provider-prefixed
  model like `anthropic:claude-sonnet-5`, capabilities array, is_active). The
  system prompt lives in the DB, not code.
- A Telegram-served agent needs its own bot token env var and a dispatcher in
  `main.py`'s lifespan (follow the workout-bot block; empty token = bot off).
  App-served agents need the slug added to `flutter_app/lib/shared/models/agent.dart`
  (ids ARE gateway slugs).
- `/health` will 503 the next deploy if the row is active but no bot is
  running for the slug or the model isn't served — that's the deploy gate
  doing its job; add the row and the runtime together.
- The classifier's agent catalog builds itself from active agents +
  capability descriptions — write the row's description-bearing fields well.

## Red flags

- A docstring that only says what the tool does → add the NOT-for boundary.
- A second httpx client for a service in the reuse list → extract instead.
- "Tests pass" without a wiring proof or count-test bumps → not done.
- Granting a capability by editing seed SQL instead of a new numbered
  migration → prod drift.
