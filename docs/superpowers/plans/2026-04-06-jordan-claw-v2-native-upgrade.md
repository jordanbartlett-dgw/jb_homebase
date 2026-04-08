# Jordan Claw v2: Native pydantic-ai 1.75 Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modernize Jordan Claw's agent construction to use pydantic-ai 1.75's native toolsets and history processors, replacing the hand-rolled TOOL_REGISTRY and manual history trimming.

**Architecture:** Evolve the existing `build_agent()` factory to use `FunctionToolset` for tool registration, `FilteredToolset` for per-agent tool scoping, and `history_processors` for automatic context window management. All tool implementations, memory, proactive messaging, Telegram, and Supabase layers stay unchanged.

**Tech Stack:** pydantic-ai 1.75 (already installed), FastAPI, Supabase, aiogram, pytest

**Spec:** `docs/superpowers/specs/2026-04-06-jordan-claw-v2-native-upgrade-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `pyproject.toml` | Modify | Pin pydantic-ai-slim version to >=1.75.0 |
| `src/jordan_claw/tools/__init__.py` | Modify | Replace TOOL_REGISTRY dict with FunctionToolset |
| `src/jordan_claw/agents/factory.py` | Modify | Use toolsets param, add history_processors, use instructions param |
| `src/jordan_claw/gateway/router.py` | Modify | Pass full history (no manual trimming) |
| `tests/test_agents.py` | Modify | Update tests for new toolset patterns |
| `tests/test_gateway.py` | No change | Gateway tests mock build_agent, unaffected |

---

### Task 1: Create Feature Branch and Pin Dependency

**Files:**
- Modify: `jordan-claw/pyproject.toml:9`

- [ ] **Step 1: Create feature branch**

```bash
cd /home/jb/Developer/jb_homebase
git checkout -b feature/v2-native-upgrade
```

- [ ] **Step 2: Pin pydantic-ai-slim version**

In `jordan-claw/pyproject.toml`, change line 9 from:
```
    "pydantic-ai-slim[anthropic]>=0.2.0",
```
To:
```
    "pydantic-ai-slim[anthropic]>=1.75.0",
```

Stay on `pydantic-ai-slim` (not full `pydantic-ai`). Toolsets and history_processors are available from slim. No new transitive deps.

- [ ] **Step 3: Sync dependencies**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv sync
```

Expected: no new packages installed (1.75.0 already in venv).

- [ ] **Step 4: Run existing tests to confirm baseline**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run pytest tests/ -v
```

Expected: all 27 tests pass. If any fail, stop and investigate before proceeding.

- [ ] **Step 5: Commit**

```bash
cd /home/jb/Developer/jb_homebase
git add jordan-claw/pyproject.toml
git commit -m "chore: pin pydantic-ai-slim to >=1.75.0 to match installed version"
```

---

### Task 2: Convert TOOL_REGISTRY to FunctionToolset

**Files:**
- Modify: `src/jordan_claw/tools/__init__.py`
- Test: `tests/test_agents.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_agents.py`:

```python
def test_base_toolset_has_all_registered_tools():
    """BASE_TOOLSET should contain all 10 tools from the old TOOL_REGISTRY."""
    from jordan_claw.tools import BASE_TOOLSET

    expected_tools = {
        "current_datetime",
        "search_web",
        "check_calendar",
        "schedule_event",
        "recall_memory",
        "forget_memory",
        "search_notes",
        "read_note",
        "create_source_note",
        "fetch_article",
    }
    # FunctionToolset exposes tool names via get_tools()
    # We need to check the internal tools dict
    registered = set(BASE_TOOLSET._tools.keys())
    assert registered == expected_tools
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run pytest tests/test_agents.py::test_base_toolset_has_all_registered_tools -v
```

Expected: FAIL with `ImportError` (BASE_TOOLSET doesn't exist yet).

- [ ] **Step 3: Implement the FunctionToolset in tools/__init__.py**

Replace the full contents of `src/jordan_claw/tools/__init__.py` with:

```python
from __future__ import annotations

from pydantic_ai.toolsets import FunctionToolset

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.tools.calendar import check_calendar, schedule_event
from jordan_claw.tools.memory import forget_memory, recall_memory
from jordan_claw.tools.obsidian import create_source_note, fetch_article, read_note, search_notes
from jordan_claw.tools.time import current_datetime
from jordan_claw.tools.web_search import search_web

BASE_TOOLSET: FunctionToolset[AgentDeps] = FunctionToolset()
BASE_TOOLSET.add_function(current_datetime, name="current_datetime")
BASE_TOOLSET.add_function(search_web, name="search_web")
BASE_TOOLSET.add_function(check_calendar, name="check_calendar")
BASE_TOOLSET.add_function(schedule_event, name="schedule_event")
BASE_TOOLSET.add_function(recall_memory, name="recall_memory")
BASE_TOOLSET.add_function(forget_memory, name="forget_memory")
BASE_TOOLSET.add_function(search_notes, name="search_notes")
BASE_TOOLSET.add_function(read_note, name="read_note")
BASE_TOOLSET.add_function(create_source_note, name="create_source_note")
BASE_TOOLSET.add_function(fetch_article, name="fetch_article")

# Keep TOOL_REGISTRY for backward compatibility during migration.
# Remove once agents/factory.py no longer references it.
TOOL_REGISTRY = {name: tool.function for name, tool in BASE_TOOLSET._tools.items()}
```

Note: the `name=` parameter on `add_function` ensures tool names match what's stored in the DB agents.tools column. Without it, pydantic-ai would derive the name from the function name, which should match anyway, but explicit is safer.

**Important:** If `_tools` is not accessible or the attribute name differs, inspect the FunctionToolset at runtime:

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
.venv/bin/python -c "
from pydantic_ai.toolsets import FunctionToolset
ts = FunctionToolset()
ts.add_function(lambda x: x, name='test')
print([a for a in dir(ts) if 'tool' in a.lower()])
print(ts._tools if hasattr(ts, '_tools') else 'no _tools attr')
"
```

Adapt the test assertion to use whichever attribute exposes tool names.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run pytest tests/test_agents.py::test_base_toolset_has_all_registered_tools -v
```

Expected: PASS

- [ ] **Step 5: Run all tests to verify no regressions**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run pytest tests/ -v
```

Expected: all tests pass (TOOL_REGISTRY backward compat keeps factory.py working).

- [ ] **Step 6: Commit**

```bash
cd /home/jb/Developer/jb_homebase
git add jordan-claw/src/jordan_claw/tools/__init__.py jordan-claw/tests/test_agents.py
git commit -m "refactor: convert TOOL_REGISTRY to FunctionToolset with backward compat"
```

---

### Task 3: Update Agent Factory to Use Toolsets

**Files:**
- Modify: `src/jordan_claw/agents/factory.py`
- Test: `tests/test_agents.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_agents.py`:

```python
@pytest.mark.asyncio
async def test_build_agent_uses_filtered_toolset():
    """build_agent should use FilteredToolset to scope tools per config."""
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="test",
        tools=["current_datetime", "search_web"],
        is_active=True,
    )

    mock_db = AsyncMock()

    with patch("jordan_claw.agents.factory.get_agent_config", return_value=fake_config):
        agent, model_name = await build_agent(mock_db, "org-001", "test-agent")

    assert model_name == "test"
    # Agent should have toolsets, not direct tools
    assert agent._toolset is not None
    # The agent should have exactly the 2 requested tools available
    # Get tool names from the toolset
    tool_defs = await agent._toolset.tool_defs()
    tool_names = {td.name for td in tool_defs}
    assert tool_names == {"current_datetime", "search_web"}
```

Add the import at the top of the test file if not present:
```python
from jordan_claw.db.agents import AgentConfig
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run pytest tests/test_agents.py::test_build_agent_uses_filtered_toolset -v
```

Expected: FAIL (current build_agent uses `tools=` param, not toolsets).

- [ ] **Step 3: Update agents/factory.py to use toolsets**

Replace the contents of `src/jordan_claw/agents/factory.py` with:

```python
from __future__ import annotations

import structlog
from pydantic_ai import Agent, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.tools import RunContext, ToolDefinition
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.agents import get_agent_config
from jordan_claw.tools import BASE_TOOLSET

log = structlog.get_logger()


def _make_tool_filter(allowed_tools: list[str]):
    """Return a filter function for FilteredToolset that allows only named tools."""
    allowed = set(allowed_tools)

    def filter_func(ctx: RunContext[AgentDeps], tool_def: ToolDefinition) -> bool:
        return tool_def.name in allowed

    return filter_func


async def build_agent(
    db: AsyncClient,
    org_id: str,
    agent_slug: str,
    memory_context: str = "",
) -> tuple[Agent[AgentDeps], str]:
    """Build a Pydantic AI agent from DB config using toolsets.

    Returns (agent, model_name) so callers can log/store the model
    without reaching into Pydantic AI internals.
    """
    config = await get_agent_config(db, org_id, agent_slug)

    # Log any tools in config that don't exist in BASE_TOOLSET
    for name in config.tools:
        if name not in BASE_TOOLSET._tools:
            log.warning("unknown_tool_skipped", tool_name=name, agent_slug=agent_slug)

    filtered = BASE_TOOLSET.filtered(_make_tool_filter(config.tools))

    system_prompt = config.system_prompt
    if memory_context:
        system_prompt = memory_context + "\n\n" + system_prompt

    agent = Agent(
        config.model,
        instructions=system_prompt,
        toolsets=[filtered],
        deps_type=AgentDeps,
    )
    return agent, config.model


CHARS_PER_TOKEN = 4


def db_messages_to_history(
    messages: list[dict],
    max_tokens: int = 4000,
) -> list[ModelRequest | ModelResponse]:
    """Convert DB message rows to Pydantic AI message history format.

    Only converts user and assistant messages. Skips system and tool roles.
    When max_tokens > 0, drops oldest messages first to stay within budget.
    Always preserves at least the most recent user+assistant exchange.
    """
    # First pass: filter to user/assistant and convert
    converted: list[tuple[ModelRequest | ModelResponse, int]] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        char_count = len(content)

        if role == "user":
            converted.append((ModelRequest(parts=[UserPromptPart(content=content)]), char_count))
        elif role == "assistant":
            converted.append((ModelResponse(parts=[TextPart(content=content)]), char_count))

    if not converted or max_tokens <= 0:
        return [item for item, _ in converted]

    # Second pass: walk newest-to-oldest, accumulate within budget
    max_chars = max_tokens * CHARS_PER_TOKEN
    kept: list[ModelRequest | ModelResponse] = []
    total_chars = 0
    for i in range(len(converted) - 1, -1, -1):
        item, char_count = converted[i]
        if total_chars + char_count > max_chars and len(kept) >= 2:
            break
        kept.append(item)
        total_chars += char_count

    kept.reverse()

    # Strip any leading assistant messages -- history must start with a user turn
    while kept and isinstance(kept[0], ModelResponse):
        kept.pop(0)

    return kept
```

Key changes from the original:
- Import `BASE_TOOLSET` instead of `TOOL_REGISTRY`
- `_make_tool_filter()` creates a filter function for FilteredToolset
- Use `BASE_TOOLSET.filtered()` to create a scoped toolset
- Use `toolsets=[filtered]` instead of `tools=tools_list`
- Use `instructions=` instead of `system_prompt=` (current pydantic-ai convention)
- `db_messages_to_history` stays unchanged (will be converted to history_processor in Task 4)

- [ ] **Step 4: Run the new test**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run pytest tests/test_agents.py::test_build_agent_uses_filtered_toolset -v
```

Expected: PASS

- [ ] **Step 5: Update existing build_agent tests**

The existing tests `test_build_agent_uses_db_config` and `test_build_agent_skips_unknown_tools` access `agent._function_toolset.tools` which may no longer work with the toolset approach. Update them:

Replace `test_build_agent_uses_db_config` (lines 116-139 in `tests/test_agents.py`) with:

```python
@pytest.mark.asyncio
async def test_build_agent_uses_db_config():
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="test",
        tools=["current_datetime", "search_web"],
        is_active=True,
    )

    mock_db = AsyncMock()

    with patch("jordan_claw.agents.factory.get_agent_config", return_value=fake_config):
        agent, model_name = await build_agent(mock_db, "org-001", "test-agent")

    assert model_name == "test"
    tool_defs = await agent._toolset.tool_defs()
    tool_names = {td.name for td in tool_defs}
    assert "current_datetime" in tool_names
    assert "search_web" in tool_names
    assert len(tool_names) == 2
```

Replace `test_build_agent_skips_unknown_tools` (lines 188-212) with:

```python
@pytest.mark.asyncio
async def test_build_agent_skips_unknown_tools():
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="test",
        tools=["current_datetime", "nonexistent_tool"],
        is_active=True,
    )

    mock_db = AsyncMock()

    with patch("jordan_claw.agents.factory.get_agent_config", return_value=fake_config):
        agent, model_name = await build_agent(mock_db, "org-001", "test-agent")

    assert model_name == "test"
    tool_defs = await agent._toolset.tool_defs()
    tool_names = {td.name for td in tool_defs}
    assert "current_datetime" in tool_names
    assert "nonexistent_tool" not in tool_names
    assert len(tool_names) == 1
```

- [ ] **Step 6: Run all tests**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run pytest tests/ -v
```

Expected: all tests pass. The gateway tests mock `build_agent` entirely and should be unaffected.

- [ ] **Step 7: Commit**

```bash
cd /home/jb/Developer/jb_homebase
git add jordan-claw/src/jordan_claw/agents/factory.py jordan-claw/tests/test_agents.py
git commit -m "refactor: use FilteredToolset for per-agent tool scoping"
```

---

### Task 4: Add History Processor for Token Budget Trimming

**Files:**
- Modify: `src/jordan_claw/agents/factory.py`
- Modify: `src/jordan_claw/gateway/router.py`
- Test: `tests/test_agents.py`

The `HistoryProcessor` signature is:
```python
Callable[[list[ModelMessage]], list[ModelMessage]]
```
or with context:
```python
Callable[[RunContext[AgentDepsT], list[ModelMessage]], list[ModelMessage]]
```

Where `ModelMessage = ModelRequest | ModelResponse`.

- [ ] **Step 1: Write the failing test for the history processor function**

Add to `tests/test_agents.py`:

```python
from pydantic_ai.messages import ModelMessage


def test_trim_history_processor_trims_to_budget():
    """trim_history_processor should drop oldest messages to stay within token budget."""
    from jordan_claw.agents.factory import trim_history_processor

    messages: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="A" * 4000)]),       # ~1000 tokens
        ModelResponse(parts=[TextPart(content="B" * 4000)]),            # ~1000 tokens
        ModelRequest(parts=[UserPromptPart(content="C" * 4000)]),       # ~1000 tokens
        ModelResponse(parts=[TextPart(content="D" * 4000)]),            # ~1000 tokens
        ModelRequest(parts=[UserPromptPart(content="E" * 400)]),        # ~100 tokens
        ModelResponse(parts=[TextPart(content="F" * 400)]),             # ~100 tokens
    ]
    result = trim_history_processor(messages)

    # Default budget is 4000 tokens (16000 chars). Total is ~4200 tokens.
    # Should drop the first exchange to fit.
    assert len(result) == 4
    assert isinstance(result[0], ModelRequest)
    assert result[0].parts[0].content == "C" * 4000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run pytest tests/test_agents.py::test_trim_history_processor_trims_to_budget -v
```

Expected: FAIL with `ImportError` (trim_history_processor doesn't exist yet).

- [ ] **Step 3: Implement trim_history_processor in factory.py**

Add this function to `src/jordan_claw/agents/factory.py`, after the `CHARS_PER_TOKEN` constant:

```python
def trim_history_processor(
    messages: list[ModelRequest | ModelResponse],
    max_tokens: int = 4000,
) -> list[ModelRequest | ModelResponse]:
    """History processor that trims oldest messages to stay within token budget.

    Always preserves at least the most recent user+assistant exchange.
    Ensures history never starts with an assistant message.
    """
    if not messages or max_tokens <= 0:
        return messages

    # Walk newest-to-oldest, accumulate within budget
    max_chars = max_tokens * CHARS_PER_TOKEN
    kept: list[ModelRequest | ModelResponse] = []
    total_chars = 0
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        char_count = sum(len(p.content) for p in msg.parts if hasattr(p, "content"))
        if total_chars + char_count > max_chars and len(kept) >= 2:
            break
        kept.append(msg)
        total_chars += char_count

    kept.reverse()

    # Strip any leading assistant messages
    while kept and isinstance(kept[0], ModelResponse):
        kept.pop(0)

    return kept
```

Then update `build_agent()` to use it. Add `history_processors=[trim_history_processor]` to the Agent constructor:

```python
    agent = Agent(
        config.model,
        instructions=system_prompt,
        toolsets=[filtered],
        history_processors=[trim_history_processor],
        deps_type=AgentDeps,
    )
```

- [ ] **Step 4: Run the new test**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run pytest tests/test_agents.py::test_trim_history_processor_trims_to_budget -v
```

Expected: PASS

- [ ] **Step 5: Simplify gateway/router.py**

In `src/jordan_claw/gateway/router.py`, the history trimming is now handled by the agent's history_processor. Change line 90 from:

```python
        history = db_messages_to_history(db_messages)
```

To:

```python
        history = db_messages_to_history(db_messages, max_tokens=0)
```

Passing `max_tokens=0` disables the manual trimming in `db_messages_to_history`, letting the agent's `trim_history_processor` handle the budget. The DB-to-ModelMessage conversion still happens.

- [ ] **Step 6: Run all tests**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run pytest tests/ -v
```

Expected: all tests pass. The gateway tests mock `build_agent` entirely so the history_processor isn't exercised in those tests, but the agent tests confirm the processor works.

- [ ] **Step 7: Commit**

```bash
cd /home/jb/Developer/jb_homebase
git add jordan-claw/src/jordan_claw/agents/factory.py jordan-claw/src/jordan_claw/gateway/router.py jordan-claw/tests/test_agents.py
git commit -m "feat: add history_processor for automatic token budget trimming"
```

---

### Task 5: Clean Up Backward Compatibility Layer

**Files:**
- Modify: `src/jordan_claw/tools/__init__.py`
- Modify: `tests/test_agents.py`

Now that `agents/factory.py` uses `BASE_TOOLSET` directly, the `TOOL_REGISTRY` backward compat dict can be removed.

- [ ] **Step 1: Check for remaining TOOL_REGISTRY references**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
grep -r "TOOL_REGISTRY" src/ tests/
```

Expected: should only appear in `tools/__init__.py` (the definition). If it appears anywhere else, those references need updating first.

- [ ] **Step 2: Remove TOOL_REGISTRY from tools/__init__.py**

Remove these lines from the bottom of `src/jordan_claw/tools/__init__.py`:

```python
# Keep TOOL_REGISTRY for backward compatibility during migration.
# Remove once agents/factory.py no longer references it.
TOOL_REGISTRY = {name: tool.function for name, tool in BASE_TOOLSET._tools.items()}
```

- [ ] **Step 3: Remove old db_messages_to_history tests that duplicate new processor tests**

The existing tests for `db_messages_to_history` (`test_history_budget_truncates_oldest_messages`, `test_history_budget_preserves_most_recent_exchange`, `test_history_no_budget_returns_all`, `test_history_budget_no_orphan_response_at_start`) still test the now-bypassed function. Keep them. They test the conversion logic which is still used. The trimming path through `db_messages_to_history` is still valid code even if the gateway no longer calls it with a budget.

- [ ] **Step 4: Run all tests**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/jb/Developer/jb_homebase
git add jordan-claw/src/jordan_claw/tools/__init__.py
git commit -m "chore: remove TOOL_REGISTRY backward compat layer"
```

---

### Task 6: Final Verification

**Files:** None (read-only verification)

- [ ] **Step 1: Run full test suite**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 2: Run ruff lint check**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run ruff check src/ tests/
```

Expected: no errors.

- [ ] **Step 3: Verify the diff is minimal**

```bash
cd /home/jb/Developer/jb_homebase
git diff main --stat
```

Expected: only these files changed:
- `jordan-claw/pyproject.toml`
- `jordan-claw/src/jordan_claw/tools/__init__.py`
- `jordan-claw/src/jordan_claw/agents/factory.py`
- `jordan-claw/src/jordan_claw/gateway/router.py`
- `jordan-claw/tests/test_agents.py`

- [ ] **Step 4: Review the full diff**

```bash
cd /home/jb/Developer/jb_homebase
git diff main
```

Scan for:
- No accidental changes to tool implementations
- No changes to memory, proactive, or Telegram code
- `instructions=` used instead of `system_prompt=`
- `toolsets=[filtered]` used instead of `tools=`
- `history_processors=[trim_history_processor]` present
- TOOL_REGISTRY fully removed
- All imports clean
