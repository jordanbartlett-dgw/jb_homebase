# Jordan Claw v2: Native pydantic-ai 1.75 Upgrade

## Context

Jordan Claw v1 is a production AI agent platform on Railway. The original v2 PRD targeted pydantic-deep as the agent runtime, but pydantic-ai 1.75 (already installed in the venv) now provides the key features natively: toolsets, history processors, builtin tools, and capabilities. This spec describes the migration path using native pydantic-ai features, avoiding a new third-party dependency.

The goal: modernize the agent construction layer to use pydantic-ai 1.75's composable patterns while keeping everything else (memory, proactive messaging, Obsidian, Telegram, Supabase) unchanged.

## Scope

### In scope
1. Pin pydantic-ai dependency to match installed version
2. Convert TOOL_REGISTRY dict to native FunctionToolset/FilteredToolset
3. Add history_processors for automatic context window management
4. Optionally add WebSearchTool as a builtin alongside existing Tavily tool

### Out of scope
- Planning/todo system (future, build as custom tools when needed)
- Sub-agent delegation (Phase 2D)
- Checkpointing / session recovery (future)
- Skills sync service (existing Supabase skills loading works)
- New Supabase tables or migrations
- Directory restructuring
- pydantic-deep dependency

## Architecture

### Current Agent Construction Flow

```
gateway/router.py: handle_message()
  -> agents/factory.py: build_agent(db, org_id, agent_slug, memory_context)
     -> Fetch agent config from Supabase (model, system_prompt, tools list)
     -> Filter TOOL_REGISTRY dict by config.tools
     -> Create Agent(model, system_prompt, tools=filtered_tools)
  -> agent.run(content, message_history=trimmed_history, deps=AgentDeps)
```

### Target Agent Construction Flow

```
gateway/router.py: handle_message()
  -> agents/factory.py: build_agent(db, org_id, agent_slug, memory_context)
     -> Fetch agent config from Supabase (model, system_prompt, tools list)
     -> Create FilteredToolset(BASE_TOOLSET, filter_fn) based on config.tools
     -> Create Agent(
            model,
            instructions=system_prompt,
            toolsets=[filtered_toolset],
            builtin_tools=[WebSearchTool()] if enabled,
            history_processors=[token_budget_trimmer],
        )
  -> agent.run(content, message_history=db_history, deps=AgentDeps)
```

### Key differences
- Tools wrapped in FunctionToolset instead of flat dict lookup
- FilteredToolset replaces manual list comprehension for per-agent tool scoping
- history_processors handles token budget trimming (currently manual in db_messages_to_history)
- DB message conversion still happens (loading from Supabase), but trimming is delegated
- AgentDeps stays unchanged

## Component Details

### 1. Dependency Pin (pyproject.toml)

Change:
```
pydantic-ai-slim[anthropic]>=0.2.0
```
To:
```
pydantic-ai[anthropic]>=1.75.0
```

Note: switching from `pydantic-ai-slim` to `pydantic-ai` to get full feature set including builtin tools. Verify this doesn't pull unwanted transitive deps.

### 2. Toolset Conversion (tools/__init__.py)

Current:
```python
TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "current_datetime": current_datetime,
    "search_web": search_web,
    ...
}
```

Target:
```python
from pydantic_ai.toolsets import FunctionToolset

BASE_TOOLSET = FunctionToolset()

# Register each tool on the toolset
# (exact registration API TBD - check FunctionToolset docs)
```

Each tool function keeps its existing signature (`RunContext[AgentDeps]`). The toolset wraps them.

### 3. Agent Factory (agents/factory.py)

Current `build_agent()` does:
1. Fetch config from DB
2. Filter tools from TOOL_REGISTRY by config.tools list
3. Build system prompt with memory context
4. Create `Agent(model, system_prompt=prompt, tools=tools_list)`

Target `build_agent()` does:
1. Fetch config from DB
2. Create `FilteredToolset(BASE_TOOLSET, filter_fn=lambda name: name in config.tools)`
3. Build system prompt with memory context
4. Create `Agent(model, instructions=prompt, toolsets=[filtered_toolset], history_processors=[trim_to_budget])`

### 4. History Processor (agents/factory.py)

Extract the token-budget logic from `db_messages_to_history()` into a function matching the HistoryProcessor signature. The DB-to-ModelMessage conversion stays separate (still needed to load from Supabase).

Current flow:
```
Load DB rows -> convert to ModelRequest/ModelResponse -> trim by token budget -> pass as message_history
```

Target flow:
```
Load DB rows -> convert to ModelRequest/ModelResponse -> pass as message_history
Agent's history_processor trims automatically before each run
```

### 5. WebSearchTool (optional, agents/factory.py)

pydantic-ai 1.75 has a builtin WebSearchTool. Options:
- **Replace Tavily**: Use WebSearchTool instead. Simpler, one less dependency. But Tavily gives more control over result formatting.
- **Complement**: Keep Tavily for deep search, add WebSearchTool for quick lookups.
- **Skip**: Keep current setup, evaluate later.

Recommendation: Skip for now. Tavily works. Evaluate after the toolset migration is stable.

## Files Changed

| File | Change |
|---|---|
| `pyproject.toml` | Pin pydantic-ai version |
| `src/jordan_claw/tools/__init__.py` | TOOL_REGISTRY -> FunctionToolset |
| `src/jordan_claw/agents/factory.py` | Use toolsets, history_processors, instructions params |
| `src/jordan_claw/gateway/router.py` | Remove manual history trimming (if history_processor handles it) |
| `tests/test_agents.py` | Update for new factory patterns |

## Files Unchanged

- All tool implementations (memory.py, obsidian.py, calendar.py, web_search.py, time.py)
- Memory system (extractor.py, reader.py, models.py)
- Proactive messaging (scheduler.py, delivery.py, executors.py)
- Telegram adapter (channels/telegram.py)
- DB layer (db/*.py)
- Obsidian pipeline (obsidian/*.py)
- Gateway models (gateway/models.py)
- Config (config.py)
- AgentDeps (agents/deps.py)

## Verification

1. Run full test suite after each step (27 existing tests should pass)
2. Verify agent construction produces working agent with correct tools
3. Verify FilteredToolset correctly scopes tools per agent config
4. Verify history_processor trims long conversations without losing recent context
5. Manual test: send messages via Telegram, confirm identical behavior to v1
6. Check Railway deploy works with updated deps

## Risks

| Risk | Mitigation |
|---|---|
| pydantic-ai-slim vs pydantic-ai transitive deps | Check what pydantic-ai full adds. If bloat, stay on slim and import toolsets separately. |
| FunctionToolset API differs from expectation | Read actual source before implementing. Registration pattern may differ. |
| history_processor signature doesn't match our trimming logic | Keep manual trimming as fallback. Migrate incrementally. |
| Existing tests break on toolset change | Tests mock Agent construction. Update mocks to match new constructor kwargs. |

## Future Work (not this spec)

- Planning/todo as custom tools (when multi-step request handling needs improvement)
- Sub-agent delegation tool
- Capability profiles in Supabase (FilteredToolset already enables per-agent scoping from existing config)
- Checkpointing for session recovery across Railway deploys
- WebSearchTool evaluation
