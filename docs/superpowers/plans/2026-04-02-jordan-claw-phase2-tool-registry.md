# Phase 2: Tool Registry + DB-Driven Agent Factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor Jordan Claw so agent config (system prompt, model, tools) loads from Supabase at runtime instead of being hardcoded in factory.py.

**Architecture:** Tool functions live in a flat `TOOL_REGISTRY` dict. A new async `build_agent()` queries the `agents` table, resolves tool names against the registry, and builds a Pydantic AI agent with `deps_type=AgentDeps`. Credentials flow through `RunContext[AgentDeps]` at tool call time, not at agent creation time.

**Tech Stack:** Pydantic AI (RunContext, Agent, Tool), Supabase (agents table), FastAPI, structlog

**Spec:** `docs/superpowers/specs/2026-04-01-jordan-claw-phase2-tool-registry-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/jordan_claw/agents/deps.py` | Create | `AgentDeps` model (credentials passed through RunContext) |
| `src/jordan_claw/db/agents.py` | Create | `AgentConfig` model + `get_agent_config()` DB query |
| `src/jordan_claw/tools/__init__.py` | Rewrite | `TOOL_REGISTRY` dict mapping string names to callables |
| `src/jordan_claw/tools/time.py` | Modify | Rename function to `current_datetime`, add tool docstring |
| `src/jordan_claw/tools/web_search.py` | Rewrite | Accept `RunContext[AgentDeps]`, rename to `search_web` |
| `src/jordan_claw/tools/calendar.py` | Modify | Add `check_calendar()` and `schedule_event()` tool wrappers accepting `RunContext[AgentDeps]`, fix `configure_calendar` idempotency |
| `src/jordan_claw/agents/factory.py` | Rewrite | Async `build_agent()` reads DB config, resolves tools from registry |
| `src/jordan_claw/gateway/router.py` | Modify | Build `AgentDeps`, pass to `agent.run(deps=...)`, call async `build_agent()` |
| `src/jordan_claw/channels/telegram.py` | Modify | Pass `agent_slug` through to `handle_message` |
| `src/jordan_claw/main.py` | Modify | Pass `agent_slug` to dispatcher |
| `tests/test_tool_registry.py` | Create | Registry completeness and tool resolution tests |
| `tests/test_agents.py` | Modify | Update for new `build_agent` signature |
| `tests/test_gateway.py` | Modify | Update for new `handle_message` signature and deps pattern |

---

### Task 1: Create AgentDeps Model

**Files:**
- Create: `src/jordan_claw/agents/deps.py`
- Test: `tests/test_agents.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_agents.py`, add at the top:

```python
from jordan_claw.agents.deps import AgentDeps


def test_agent_deps_construction():
    deps = AgentDeps(
        org_id="test-org",
        tavily_api_key="tavily-key",
        fastmail_username="user@fastmail.com",
        fastmail_app_password="app-pass",
    )
    assert deps.org_id == "test-org"
    assert deps.tavily_api_key == "tavily-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jordan-claw && uv run pytest tests/test_agents.py::test_agent_deps_construction -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.agents.deps'`

- [ ] **Step 3: Implement AgentDeps**

Create `src/jordan_claw/agents/deps.py`:

```python
from __future__ import annotations

from pydantic import BaseModel


class AgentDeps(BaseModel):
    """Credentials and context passed to tools via RunContext[AgentDeps]."""

    org_id: str
    tavily_api_key: str
    fastmail_username: str
    fastmail_app_password: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jordan-claw && uv run pytest tests/test_agents.py::test_agent_deps_construction -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jordan-claw/src/jordan_claw/agents/deps.py jordan-claw/tests/test_agents.py
git commit -m "feat: add AgentDeps model for RunContext credential injection"
```

---

### Task 2: Refactor Tool Functions for Deps Pattern

**Files:**
- Modify: `src/jordan_claw/tools/time.py`
- Rewrite: `src/jordan_claw/tools/web_search.py`
- Modify: `src/jordan_claw/tools/calendar.py`

- [ ] **Step 1: Refactor time.py**

Rename function so Pydantic AI uses "current_datetime" as the tool name. Replace the full file:

```python
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def current_datetime() -> str:
    """Get the current date and time in US Central time."""
    now = datetime.now(ZoneInfo("America/Chicago"))
    return now.strftime("%Y-%m-%d %H:%M:%S %Z (%A)")
```

- [ ] **Step 2: Refactor web_search.py**

Rename function to `search_web`, accept `RunContext[AgentDeps]` as first param. Replace the full file:

```python
from __future__ import annotations

from pydantic_ai import RunContext
from tavily import AsyncTavilyClient

from jordan_claw.agents.deps import AgentDeps


async def search_web(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search the web for current information.

    Use for questions about recent events, facts, or anything
    that benefits from up-to-date data.
    """
    client = AsyncTavilyClient(api_key=ctx.deps.tavily_api_key)
    response = await client.search(query=query, max_results=3)

    results = response.get("results", [])
    if not results:
        return "No results found."

    formatted = []
    for r in results:
        title = r.get("title", "No title")
        url = r.get("url", "")
        snippet = r.get("content", "No description")
        formatted.append(f"**{title}**\n{snippet}\n{url}")

    return "\n\n---\n\n".join(formatted)
```

- [ ] **Step 3: Fix configure_calendar idempotency and add tool wrappers to calendar.py**

In `src/jordan_claw/tools/calendar.py`, make two changes:

**Change 1:** Fix `configure_calendar` to skip if credentials unchanged (lines 30-35):

Replace:
```python
def configure_calendar(username: str, app_password: str) -> None:
    """Store Fastmail CalDAV credentials for later use."""
    global _username, _app_password, _calendar_cache
    _username = username
    _app_password = app_password
    _calendar_cache = None  # reset cache when credentials change
```

With:
```python
def configure_calendar(username: str, app_password: str) -> None:
    """Store Fastmail CalDAV credentials for later use."""
    global _username, _app_password, _calendar_cache
    if _username == username and _app_password == app_password:
        return
    _username = username
    _app_password = app_password
    _calendar_cache = None
```

**Change 2:** Add tool wrapper functions at the end of the file (after `create_calendar_event`):

```python
async def check_calendar(
    ctx: RunContext[AgentDeps], start_date: str, end_date: str
) -> str:
    """Check Jordan's calendar for events in a date range.

    Args:
        start_date: Start date as YYYY-MM-DD
        end_date: End date as YYYY-MM-DD
    """
    configure_calendar(ctx.deps.fastmail_username, ctx.deps.fastmail_app_password)
    return await get_calendar_events(start_date, end_date)


async def schedule_event(
    ctx: RunContext[AgentDeps],
    title: str,
    start: str,
    end: str,
    location: str | None = None,
    description: str | None = None,
) -> str:
    """Create a new event on Jordan's calendar.

    Args:
        title: Event title
        start: Start datetime as YYYY-MM-DDTHH:MM:SS
        end: End datetime as YYYY-MM-DDTHH:MM:SS
        location: Optional location
        description: Optional description
    """
    configure_calendar(ctx.deps.fastmail_username, ctx.deps.fastmail_app_password)
    return await create_calendar_event(title, start, end, location, description)
```

These wrappers need the RunContext import at the top of calendar.py:

```python
from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
```

- [ ] **Step 4: Run existing calendar tests to verify nothing broke**

Run: `cd jordan-claw && uv run pytest tests/test_calendar.py -v`
Expected: All existing tests PASS (utility functions unchanged)

- [ ] **Step 5: Lint**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/tools/ --fix && uv run ruff format src/jordan_claw/tools/`

- [ ] **Step 6: Commit**

```bash
git add jordan-claw/src/jordan_claw/tools/
git commit -m "refactor: convert tool functions to deps pattern with RunContext[AgentDeps]"
```

---

### Task 3: Create TOOL_REGISTRY

**Files:**
- Rewrite: `src/jordan_claw/tools/__init__.py`
- Create: `tests/test_tool_registry.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tool_registry.py`:

```python
from __future__ import annotations

import inspect

from jordan_claw.tools import TOOL_REGISTRY


EXPECTED_TOOLS = ["current_datetime", "search_web", "check_calendar", "schedule_event"]


def test_registry_has_all_expected_tools():
    for name in EXPECTED_TOOLS:
        assert name in TOOL_REGISTRY, f"Missing tool: {name}"


def test_registry_has_no_unexpected_tools():
    assert set(TOOL_REGISTRY.keys()) == set(EXPECTED_TOOLS)


def test_registry_values_are_callable():
    for name, func in TOOL_REGISTRY.items():
        assert callable(func), f"{name} is not callable"


def test_plain_tools_have_no_ctx_param():
    """current_datetime should not accept RunContext."""
    sig = inspect.signature(TOOL_REGISTRY["current_datetime"])
    param_names = list(sig.parameters.keys())
    assert "ctx" not in param_names


def test_deps_tools_have_ctx_param():
    """Tools needing credentials should accept RunContext as first param."""
    for name in ["search_web", "check_calendar", "schedule_event"]:
        sig = inspect.signature(TOOL_REGISTRY[name])
        first_param = list(sig.parameters.keys())[0]
        assert first_param == "ctx", f"{name} first param should be 'ctx', got '{first_param}'"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_tool_registry.py -v`
Expected: FAIL with `ImportError: cannot import name 'TOOL_REGISTRY'`

- [ ] **Step 3: Implement TOOL_REGISTRY**

Replace `src/jordan_claw/tools/__init__.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jordan_claw.tools.calendar import check_calendar, schedule_event
from jordan_claw.tools.time import current_datetime
from jordan_claw.tools.web_search import search_web

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "current_datetime": current_datetime,
    "search_web": search_web,
    "check_calendar": check_calendar,
    "schedule_event": schedule_event,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_tool_registry.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add jordan-claw/src/jordan_claw/tools/__init__.py jordan-claw/tests/test_tool_registry.py
git commit -m "feat: add TOOL_REGISTRY mapping tool names to callables"
```

---

### Task 4: Create get_agent_config DB Function

**Files:**
- Modify: `src/jordan_claw/db/agents.py`
- Create test in: `tests/test_agents.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_agents.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from jordan_claw.db.agents import AgentConfig, get_agent_config


@pytest.mark.asyncio
async def test_get_agent_config_returns_typed_config():
    mock_db = AsyncMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
        return_value=MagicMock(
            data=[
                {
                    "id": "agent-001",
                    "org_id": "org-001",
                    "name": "Test Agent",
                    "slug": "test-agent",
                    "system_prompt": "You are helpful.",
                    "model": "claude-sonnet-4-20250514",
                    "tools": ["current_datetime", "search_web"],
                    "is_active": True,
                }
            ]
        )
    )

    config = await get_agent_config(mock_db, "org-001", "test-agent")

    assert isinstance(config, AgentConfig)
    assert config.slug == "test-agent"
    assert config.tools == ["current_datetime", "search_web"]
    assert config.system_prompt == "You are helpful."


@pytest.mark.asyncio
async def test_get_agent_config_not_found_raises():
    mock_db = AsyncMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[])
    )

    with pytest.raises(ValueError, match="Agent not found"):
        await get_agent_config(mock_db, "org-001", "missing-agent")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_agents.py::test_get_agent_config_returns_typed_config tests/test_agents.py::test_get_agent_config_not_found_raises -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Implement get_agent_config**

Create `src/jordan_claw/db/agents.py`:

```python
from __future__ import annotations

import structlog
from pydantic import BaseModel
from supabase._async.client import AsyncClient

log = structlog.get_logger()


class AgentConfig(BaseModel):
    """Typed representation of an agent row from the agents table."""

    id: str
    org_id: str
    name: str
    slug: str
    system_prompt: str
    model: str
    tools: list[str]
    is_active: bool


async def get_agent_config(
    client: AsyncClient, org_id: str, slug: str
) -> AgentConfig:
    """Fetch a single active agent config by org_id and slug."""
    result = (
        await client.table("agents")
        .select("id, org_id, name, slug, system_prompt, model, tools, is_active")
        .eq("org_id", org_id)
        .eq("slug", slug)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise ValueError(f"Agent not found: org_id={org_id}, slug={slug}")

    return AgentConfig.model_validate(result.data[0])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_agents.py::test_get_agent_config_returns_typed_config tests/test_agents.py::test_get_agent_config_not_found_raises -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add jordan-claw/src/jordan_claw/db/agents.py jordan-claw/tests/test_agents.py
git commit -m "feat: add get_agent_config to read agent config from Supabase"
```

---

### Task 5: Rewrite factory.py for DB-Driven Agent Creation

**Files:**
- Rewrite: `src/jordan_claw/agents/factory.py`
- Test: `tests/test_agents.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_agents.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from jordan_claw.agents.factory import build_agent
from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.agents import AgentConfig


@pytest.mark.asyncio
async def test_build_agent_uses_db_config():
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="claude-sonnet-4-20250514",
        tools=["current_datetime", "search_web"],
        is_active=True,
    )

    mock_db = AsyncMock()

    with patch("jordan_claw.agents.factory.get_agent_config", return_value=fake_config):
        agent = await build_agent(mock_db, "org-001", "test-agent")

    assert agent.model.model_name() == "claude-sonnet-4-20250514"
    # Agent should have exactly 2 tools
    tool_names = {t.name for t in agent._function_tools.values()}
    assert "current_datetime" in tool_names
    assert "search_web" in tool_names
    assert len(tool_names) == 2


@pytest.mark.asyncio
async def test_build_agent_skips_unknown_tools():
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="claude-sonnet-4-20250514",
        tools=["current_datetime", "nonexistent_tool"],
        is_active=True,
    )

    mock_db = AsyncMock()

    with patch("jordan_claw.agents.factory.get_agent_config", return_value=fake_config):
        agent = await build_agent(mock_db, "org-001", "test-agent")

    tool_names = {t.name for t in agent._function_tools.values()}
    assert "current_datetime" in tool_names
    assert "nonexistent_tool" not in tool_names
    assert len(tool_names) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_agents.py::test_build_agent_uses_db_config tests/test_agents.py::test_build_agent_skips_unknown_tools -v`
Expected: FAIL with `ImportError: cannot import name 'build_agent'`

- [ ] **Step 3: Rewrite factory.py**

Replace `src/jordan_claw/agents/factory.py` entirely:

```python
from __future__ import annotations

import structlog
from pydantic_ai import Agent, ModelRequest, ModelResponse, TextPart, UserPromptPart
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.agents import get_agent_config
from jordan_claw.tools import TOOL_REGISTRY

log = structlog.get_logger()


async def build_agent(
    db: AsyncClient,
    org_id: str,
    agent_slug: str,
) -> Agent[AgentDeps]:
    """Build a Pydantic AI agent from DB config and the tool registry."""
    config = await get_agent_config(db, org_id, agent_slug)

    tools = []
    for name in config.tools:
        if name in TOOL_REGISTRY:
            tools.append(TOOL_REGISTRY[name])
        else:
            log.warning("unknown_tool_skipped", tool_name=name, agent_slug=agent_slug)

    return Agent(
        config.model,
        system_prompt=config.system_prompt,
        tools=tools,
        deps_type=AgentDeps,
    )


def db_messages_to_history(messages: list[dict]) -> list[ModelRequest | ModelResponse]:
    """Convert DB message rows to Pydantic AI message history format.

    Only converts user and assistant messages. Skips system and tool roles.
    """
    history: list[ModelRequest | ModelResponse] = []

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=content)]))

    return history
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_agents.py -v`
Expected: All PASS (including existing `db_messages_to_history` tests and new tests)

Note: The `test_build_agent_uses_db_config` test inspects `agent.model.model_name()` and `agent._function_tools`. If `model_name()` is not the right accessor, check the Pydantic AI `Agent` API. The internal `_function_tools` dict maps tool name to `Tool` object. If this internal API has changed, adjust assertions to verify tool count and names through whatever public API is available.

- [ ] **Step 5: Lint**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/agents/ --fix && uv run ruff format src/jordan_claw/agents/`

- [ ] **Step 6: Commit**

```bash
git add jordan-claw/src/jordan_claw/agents/factory.py jordan-claw/tests/test_agents.py
git commit -m "feat: rewrite agent factory to load config from Supabase"
```

---

### Task 6: Update Gateway Chain (Router + Telegram + Main)

**Files:**
- Modify: `src/jordan_claw/gateway/router.py`
- Modify: `src/jordan_claw/channels/telegram.py`
- Modify: `src/jordan_claw/main.py`
- Modify: `tests/test_gateway.py`

- [ ] **Step 1: Update test_gateway.py for new signatures**

Replace `tests/test_gateway.py` entirely:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.gateway.models import IncomingMessage
from jordan_claw.gateway.router import ERROR_RESPONSE, handle_message


def make_incoming(
    content: str = "Hello",
    channel_message_id: str = "telegram:123",
) -> IncomingMessage:
    return IncomingMessage(
        channel="telegram",
        channel_thread_id="chat_456",
        channel_message_id=channel_message_id,
        content=content,
        org_id="1408252a-fd36-4fd3-b527-3b2f495d7b9c",
    )


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.mark.asyncio
async def test_duplicate_message_returns_empty(mock_db):
    """Duplicate messages should be skipped."""
    with patch("jordan_claw.gateway.router.message_exists", return_value=True):
        result = await handle_message(
            make_incoming(),
            db=mock_db,
            agent_slug="claw-main",
            tavily_api_key="test-key",
            fastmail_username="test@fastmail.com",
            fastmail_app_password="test-password",
        )

    assert result.content == ""
    assert result.conversation_id == ""


@pytest.mark.asyncio
async def test_successful_message_flow(mock_db):
    """A normal message should go through the full lifecycle and return a response."""
    fake_conversation = {"id": "conv-001"}
    fake_messages = [
        {
            "role": "user",
            "content": "Hi",
            "created_at": "2026-01-01T00:00:00Z",
            "token_count": None,
            "model": None,
            "metadata": {},
        },
    ]

    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_usage.requests = 1

    mock_result = MagicMock()
    mock_result.output = "Hello! How can I help?"
    mock_result.usage.return_value = mock_usage

    mock_agent = AsyncMock()
    mock_agent.run.return_value = mock_result

    with (
        patch("jordan_claw.gateway.router.message_exists", return_value=False),
        patch(
            "jordan_claw.gateway.router.get_or_create_conversation",
            return_value=fake_conversation,
        ),
        patch("jordan_claw.gateway.router.save_message", return_value={}),
        patch(
            "jordan_claw.gateway.router.get_recent_messages",
            return_value=fake_messages,
        ),
        patch(
            "jordan_claw.gateway.router.build_agent",
            return_value=mock_agent,
        ),
    ):
        result = await handle_message(
            make_incoming(),
            db=mock_db,
            agent_slug="claw-main",
            tavily_api_key="test-key",
            fastmail_username="test@fastmail.com",
            fastmail_app_password="test-password",
        )

    assert result.content == "Hello! How can I help?"
    assert result.conversation_id == "conv-001"
    assert result.token_count == 15
    assert result.model == "claude-sonnet-4-20250514"

    # Verify deps were passed to agent.run
    call_kwargs = mock_agent.run.call_args.kwargs
    assert "deps" in call_kwargs
    assert call_kwargs["deps"].org_id == "1408252a-fd36-4fd3-b527-3b2f495d7b9c"
    assert call_kwargs["deps"].tavily_api_key == "test-key"


@pytest.mark.asyncio
async def test_agent_error_returns_friendly_message(mock_db):
    """Agent failures should return a user-friendly error, not crash."""
    fake_conversation = {"id": "conv-002"}

    with (
        patch("jordan_claw.gateway.router.message_exists", return_value=False),
        patch(
            "jordan_claw.gateway.router.get_or_create_conversation",
            return_value=fake_conversation,
        ),
        patch("jordan_claw.gateway.router.save_message", return_value={}),
        patch("jordan_claw.gateway.router.get_recent_messages", return_value=[]),
        patch(
            "jordan_claw.gateway.router.build_agent",
            side_effect=Exception("LLM timeout"),
        ),
        patch(
            "jordan_claw.gateway.router.update_conversation_status",
            return_value=None,
        ),
    ):
        result = await handle_message(
            make_incoming(channel_message_id="telegram:999"),
            db=mock_db,
            agent_slug="claw-main",
            tavily_api_key="test-key",
            fastmail_username="test@fastmail.com",
            fastmail_app_password="test-password",
        )

    assert result.content == ERROR_RESPONSE
    assert result.conversation_id == "conv-002"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_gateway.py -v`
Expected: FAIL (signature mismatch, `build_agent` not found in router)

- [ ] **Step 3: Rewrite gateway/router.py**

Replace `src/jordan_claw/gateway/router.py`:

```python
from __future__ import annotations

import time

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import build_agent, db_messages_to_history
from jordan_claw.db.conversations import get_or_create_conversation, update_conversation_status
from jordan_claw.db.messages import get_recent_messages, message_exists, save_message
from jordan_claw.gateway.models import GatewayResponse, IncomingMessage
from jordan_claw.utils.token_counting import extract_usage

logger = structlog.get_logger()

ERROR_RESPONSE = "Something went wrong. Try again."


async def handle_message(
    msg: IncomingMessage,
    *,
    db: AsyncClient,
    agent_slug: str,
    tavily_api_key: str,
    fastmail_username: str,
    fastmail_app_password: str,
    history_limit: int = 50,
    environment: str = "development",
) -> GatewayResponse:
    """Process an incoming message through the full gateway lifecycle."""
    log = logger.bind(
        org_id=msg.org_id,
        channel=msg.channel,
        channel_thread_id=msg.channel_thread_id,
    )

    # 1. Dedup
    if await message_exists(db, msg.channel_message_id):
        log.info("duplicate_message_skipped", channel_message_id=msg.channel_message_id)
        return GatewayResponse(content="", conversation_id="")

    # 2. Get or create conversation
    conversation = await get_or_create_conversation(
        db, msg.org_id, msg.channel, msg.channel_thread_id
    )
    conversation_id = conversation["id"]
    log = log.bind(conversation_id=conversation_id, agent_slug=agent_slug)

    # 3. Save user message
    await save_message(
        db,
        conversation_id=conversation_id,
        role="user",
        content=msg.content,
        channel_message_id=msg.channel_message_id,
    )

    # 4. Load history
    db_messages = await get_recent_messages(db, conversation_id, limit=history_limit)

    # 5. Build agent from DB config, run with deps
    try:
        start = time.monotonic()

        agent = await build_agent(db, msg.org_id, agent_slug)
        deps = AgentDeps(
            org_id=msg.org_id,
            tavily_api_key=tavily_api_key,
            fastmail_username=fastmail_username,
            fastmail_app_password=fastmail_app_password,
        )
        history = db_messages_to_history(db_messages)

        result = await agent.run(msg.content, message_history=history, deps=deps)

        latency_ms = int((time.monotonic() - start) * 1000)
        response_text = result.output
        usage = extract_usage(result.usage())
        model_name = "claude-sonnet-4-20250514"

        if environment == "development":
            log.debug("agent_message_content", content=msg.content, response=response_text)

        log.info(
            "agent_run_complete",
            status="success",
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
            model=model_name,
            latency_ms=latency_ms,
        )

    except Exception:
        log.exception("agent_run_failed", status="error")
        await update_conversation_status(db, conversation_id, "error")
        await save_message(
            db,
            conversation_id=conversation_id,
            role="assistant",
            content=ERROR_RESPONSE,
        )
        return GatewayResponse(content=ERROR_RESPONSE, conversation_id=conversation_id)

    # 6. Save assistant response
    await save_message(
        db,
        conversation_id=conversation_id,
        role="assistant",
        content=response_text,
        token_count=usage["total_tokens"],
        model=model_name,
    )

    # 7. Return
    return GatewayResponse(
        content=response_text,
        conversation_id=conversation_id,
        token_count=usage["total_tokens"],
        model=model_name,
    )
```

- [ ] **Step 4: Run gateway tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_gateway.py -v`
Expected: All PASS

- [ ] **Step 5: Update telegram.py**

In `src/jordan_claw/channels/telegram.py`, add `agent_slug` parameter.

Replace the function signature at lines 14-24:

```python
def create_telegram_dispatcher(
    bot: Bot,
    *,
    db: AsyncClient,
    default_org_id: str,
    agent_slug: str,
    tavily_api_key: str,
    fastmail_username: str,
    fastmail_app_password: str,
    history_limit: int,
    environment: str,
) -> Dispatcher:
```

And update the `handle_message` call inside `handle_text` (lines 51-59) to pass `agent_slug`:

```python
        response = await handle_message(
            incoming,
            db=db,
            agent_slug=agent_slug,
            tavily_api_key=tavily_api_key,
            fastmail_username=fastmail_username,
            fastmail_app_password=fastmail_app_password,
            history_limit=history_limit,
            environment=environment,
        )
```

- [ ] **Step 6: Update main.py**

In `src/jordan_claw/main.py`, pass `agent_slug` to the dispatcher (line 59-68):

```python
    dp = create_telegram_dispatcher(
        bot,
        db=db,
        default_org_id=settings.default_org_id,
        agent_slug=settings.default_agent_slug,
        tavily_api_key=settings.tavily_api_key,
        fastmail_username=settings.fastmail_username,
        fastmail_app_password=settings.fastmail_app_password,
        history_limit=settings.message_history_limit,
        environment=settings.environment,
    )
```

- [ ] **Step 7: Run all tests**

Run: `cd jordan-claw && uv run pytest -v`
Expected: All tests PASS

- [ ] **Step 8: Lint**

Run: `cd jordan-claw && uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/`

- [ ] **Step 9: Commit**

```bash
git add jordan-claw/src/jordan_claw/gateway/router.py jordan-claw/src/jordan_claw/channels/telegram.py jordan-claw/src/jordan_claw/main.py jordan-claw/tests/test_gateway.py
git commit -m "feat: wire DB-driven agent factory through gateway chain"
```

---

## Verification Checklist

After all tasks are complete, verify the spec's success criteria:

- [ ] **Agent config from DB:** `build_agent()` calls `get_agent_config()` which queries the `agents` table. System prompt, model, and tools come from the row, not hardcoded values.
- [ ] **Dynamic tools:** Changing the `tools` JSON array in the `agents` table changes which tools the agent has on the next message (each message builds a fresh agent).
- [ ] **Adding a tool:** Write a function, add it to `TOOL_REGISTRY` in `tools/__init__.py`, add the name to the agent's `tools` column. No other code changes needed.
- [ ] **Existing behavior preserved:** Run the bot locally (`cd jordan-claw && uv run uvicorn jordan_claw.main:app`), send a Telegram message, verify calendar/web search/datetime tools still work.
- [ ] **All tests pass:** `cd jordan-claw && uv run pytest -v`
- [ ] **Lint clean:** `cd jordan-claw && uv run ruff check src/ tests/`
