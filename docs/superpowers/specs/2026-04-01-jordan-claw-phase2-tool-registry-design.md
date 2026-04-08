# Phase 2: Tool Registry + DB-Driven Agent Factory

**Date:** 2026-04-01
**Scope:** Refactor Jordan Claw so agent config (system prompt, model, tools) is loaded from Supabase at runtime. Adding a new tool means writing a Python function, registering it, and updating the agent's `tools` column.

## Decisions

- **Agent creation:** per-message, no caching. Revisit at higher volume or when sub-agents land.
- **Tool credentials:** Pydantic AI deps pattern (`RunContext[AgentDeps]`), not closures.
- **System prompt source:** DB only, no hardcoded fallback. Agent already depends on Supabase for conversations.
- **Unknown tool names:** log warning, skip. Agent works with whatever tools matched.
- **No agent routing:** single agent (claw-main). Routing deferred until a second agent exists.

## Architecture

### AgentDeps Model

New file: `src/jordan_claw/agents/deps.py`

```python
class AgentDeps(BaseModel):
    org_id: str
    tavily_api_key: str
    fastmail_username: str
    fastmail_app_password: str
```

All tools needing credentials receive this via `RunContext[AgentDeps]`. Tools without credential needs (e.g. `current_datetime`) use `@agent.tool_plain`.

### Tool Registry

`tools/__init__.py` exports a flat dict mapping string identifiers to functions:

```python
TOOL_REGISTRY: dict[str, Callable] = {
    "current_datetime": get_current_datetime,
    "search_web": search_web,
    "check_calendar": check_calendar,
    "schedule_event": schedule_event,
}
```

New tools are added here. The registry is the single source of truth for available tools. Both deps-aware tools (accepting `RunContext[AgentDeps]`) and plain tools (no context) live in the same registry. Pydantic AI handles both signatures when registering tools on the agent.

### Agent Factory (refactored)

`agents/factory.py` becomes:

1. Query `agents` table by org_id + slug
2. Read `system_prompt`, `model`, `tools` (JSON array of string identifiers)
3. Look up each tool name in `TOOL_REGISTRY`. Unknown names get a warning log and are skipped.
4. Build Pydantic AI agent with matched tools, DB system prompt, DB model
5. Return agent

### DB Access

New file: `src/jordan_claw/db/agents.py`

- `get_agent_config(client, org_id, slug)` — fetch a single agent row, return typed result

### Gateway Changes

`gateway/router.py` builds an `AgentDeps` instance from settings and passes it to `agent.run()` via the `deps` parameter. Credentials no longer passed to `create_agent()`.

## File Changes

| File | Action |
|---|---|
| `src/jordan_claw/agents/factory.py` | Rewrite: query DB, build agent from config, use deps pattern |
| `src/jordan_claw/agents/deps.py` | New: `AgentDeps` model |
| `src/jordan_claw/tools/__init__.py` | New: `TOOL_REGISTRY` dict |
| `src/jordan_claw/tools/calendar.py` | Refactor: tools accept `RunContext[AgentDeps]` |
| `src/jordan_claw/tools/web_search.py` | Refactor: tool accepts `RunContext[AgentDeps]` |
| `src/jordan_claw/tools/time.py` | No change (no deps needed) |
| `src/jordan_claw/db/agents.py` | New: `get_agent_config()` |
| `src/jordan_claw/gateway/router.py` | Refactor: build `AgentDeps`, pass to agent run |
| `tests/test_agents.py` | Update for new factory signature |

## What Does NOT Change

- Supabase schema (agents table already has the right columns)
- Telegram adapter
- Message persistence (conversations.py, messages.py)
- Deployment config

## Success Criteria

- Agent system prompt, model, and tool list come from the `agents` table, not hardcoded
- Changing the `tools` JSON array in Supabase changes which tools the agent has on the next message
- Adding a new tool = write a function, add to `TOOL_REGISTRY`, add the name to the agent's `tools` column
- Existing behavior unchanged: Jordan messages from Telegram, gets responses with calendar/web search/datetime

## Deferred Decisions

Tracked in memory (`project_phase2_deferred_decisions.md`):

1. Agent caching — revisit at higher volume or Phase 3
2. Agent routing — revisit when a second agent is added
3. Fail-hard on unknown tools — revisit when clients configure their own agents
