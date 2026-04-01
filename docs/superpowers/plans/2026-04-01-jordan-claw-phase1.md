# Jordan Claw Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Jordan Claw MVP: a FastAPI + aiogram process that receives Telegram messages, routes them through a Pydantic AI agent with conversation history from Supabase, and deploys to Railway.

**Architecture:** Single process runs FastAPI (health check, future HTTP routes) and aiogram (Telegram long-polling) on the same asyncio event loop. The Telegram handler calls the gateway router as a direct async function call. The gateway loads/saves conversation state in Supabase and runs a Pydantic AI agent with message history. Channel-agnostic models (IncomingMessage, GatewayResponse) prep for future HTTP routes.

**Tech Stack:** Python 3.12, FastAPI, Pydantic AI, aiogram 3.x, supabase-py (async), Tavily, structlog, pydantic-settings, uv, Railway

---

## File Map

| File | Responsibility |
|---|---|
| `jordan-claw/pyproject.toml` | Project metadata, all dependencies |
| `jordan-claw/.env.example` | Template for required env vars |
| `jordan-claw/Dockerfile` | Production container (Python 3.12 slim + uv) |
| `jordan-claw/src/jordan_claw/__init__.py` | Package marker |
| `jordan-claw/src/jordan_claw/config.py` | Settings via pydantic-settings |
| `jordan-claw/src/jordan_claw/main.py` | FastAPI app, lifespan, structlog config, /health |
| `jordan-claw/src/jordan_claw/gateway/__init__.py` | Package marker |
| `jordan-claw/src/jordan_claw/gateway/models.py` | IncomingMessage, GatewayResponse |
| `jordan-claw/src/jordan_claw/gateway/router.py` | handle_message() core function |
| `jordan-claw/src/jordan_claw/channels/__init__.py` | Package marker |
| `jordan-claw/src/jordan_claw/channels/telegram.py` | aiogram adapter |
| `jordan-claw/src/jordan_claw/agents/__init__.py` | Package marker |
| `jordan-claw/src/jordan_claw/agents/factory.py` | Agent creation, message history conversion |
| `jordan-claw/src/jordan_claw/tools/__init__.py` | Package marker |
| `jordan-claw/src/jordan_claw/tools/time.py` | Current datetime tool |
| `jordan-claw/src/jordan_claw/tools/web_search.py` | Tavily search tool |
| `jordan-claw/src/jordan_claw/db/__init__.py` | Package marker |
| `jordan-claw/src/jordan_claw/db/client.py` | Async Supabase client singleton |
| `jordan-claw/src/jordan_claw/db/conversations.py` | Conversation CRUD |
| `jordan-claw/src/jordan_claw/db/messages.py` | Message CRUD |
| `jordan-claw/src/jordan_claw/utils/__init__.py` | Package marker |
| `jordan-claw/src/jordan_claw/utils/token_counting.py` | Extract token/usage from agent result |
| `jordan-claw/tests/__init__.py` | Package marker |
| `jordan-claw/tests/test_gateway.py` | Gateway router unit tests |
| `jordan-claw/supabase/migrations/001_initial_schema.sql` | Full schema, indexes, RLS, seed data |

---

### Task 1: Project Scaffold and Dependencies

**Files:**
- Create: `jordan-claw/pyproject.toml`
- Create: `jordan-claw/.env.example`
- Create: `jordan-claw/.gitignore`
- Create: `jordan-claw/src/jordan_claw/__init__.py`
- Create: `jordan-claw/tests/__init__.py`

- [ ] **Step 1: Create project directory**

```bash
mkdir -p jordan-claw/src/jordan_claw jordan-claw/tests
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[project]
name = "jordan-claw"
version = "0.1.0"
description = "Multi-tenant, multi-channel AI agent gateway"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic-ai-slim[anthropic]>=0.2.0",
    "pydantic-settings>=2.5.0",
    "supabase>=2.11.0",
    "aiogram>=3.13.0",
    "tavily-python>=0.5.0",
    "structlog>=24.4.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.7.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/jordan_claw"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM"]
```

- [ ] **Step 3: Create .env.example**

```
ANTHROPIC_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_ANON_KEY=
TELEGRAM_BOT_TOKEN=
TAVILY_API_KEY=
DEFAULT_ORG_ID=
```

- [ ] **Step 4: Create .gitignore**

```
__pycache__/
*.pyc
.env
.venv/
*.egg-info/
dist/
.ruff_cache/
.pytest_cache/
uv.lock
```

- [ ] **Step 5: Create package init files**

`jordan-claw/src/jordan_claw/__init__.py`:
```python
from __future__ import annotations
```

`jordan-claw/tests/__init__.py`:
```python
from __future__ import annotations
```

- [ ] **Step 6: Initialize uv and install dependencies**

```bash
cd jordan-claw && uv sync
```

Expected: `uv.lock` created, all dependencies installed.

- [ ] **Step 7: Verify ruff works**

```bash
cd jordan-claw && uv run ruff check src/ tests/
```

Expected: No errors (empty project).

- [ ] **Step 8: Commit**

```bash
git add jordan-claw/
git commit -m "chore: scaffold jordan-claw project with dependencies"
```

---

### Task 2: Configuration

**Files:**
- Create: `jordan-claw/src/jordan_claw/config.py`

- [ ] **Step 1: Create config.py**

```python
from __future__ import annotations

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str
    anthropic_api_key: str
    telegram_bot_token: str
    tavily_api_key: str
    default_org_id: str
    default_agent_slug: str = "claw-main"
    log_level: str = "INFO"
    environment: str = "development"
    message_history_limit: int = 50

    model_config = ConfigDict(env_file=".env")


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 2: Verify it loads (quick smoke test)**

```bash
cd jordan-claw && infisical run -- uv run python -c "from jordan_claw.config import get_settings; s = get_settings(); print(s.supabase_url)"
```

Expected: Prints the Supabase URL from Infisical.

- [ ] **Step 3: Commit**

```bash
git add jordan-claw/src/jordan_claw/config.py
git commit -m "feat: add pydantic-settings configuration"
```

---

### Task 3: Database Schema Migration

**Files:**
- Create: `jordan-claw/supabase/migrations/001_initial_schema.sql`

- [ ] **Step 1: Create migration file**

```sql
-- Jordan Claw Phase 1 Schema
-- Run this in the Supabase SQL Editor

-- Organizations (tenants)
create table organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    slug text unique not null,
    settings jsonb default '{}',
    created_at timestamptz default now()
);

-- Agent definitions per organization (read by Phase 2 code, exists for schema readiness)
create table agents (
    id uuid primary key default gen_random_uuid(),
    org_id uuid references organizations(id) on delete cascade,
    name text not null,
    slug text not null,
    system_prompt text not null,
    model text default 'claude-sonnet-4-20250514',
    tools jsonb default '[]',
    settings jsonb default '{}',
    is_default boolean default false,
    is_active boolean default true,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique(org_id, slug)
);

-- Conversations track a thread across any channel
create table conversations (
    id uuid primary key default gen_random_uuid(),
    org_id uuid references organizations(id) on delete cascade,
    agent_id uuid references agents(id),
    channel text not null,
    channel_thread_id text,
    user_id uuid,
    metadata jsonb default '{}',
    status text default 'active' check (status in ('active', 'archived', 'error')),
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- Messages within a conversation
create table messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid references conversations(id) on delete cascade,
    role text not null check (role in ('user', 'assistant', 'system', 'tool')),
    content text not null,
    channel_message_id text,
    token_count int,
    cost_usd numeric(10, 6),
    model text,
    metadata jsonb default '{}',
    created_at timestamptz default now()
);

-- Indexes
create index idx_messages_conversation_created on messages(conversation_id, created_at);
create index idx_messages_channel_dedup on messages(channel_message_id) where channel_message_id is not null;
create index idx_conversations_channel on conversations(org_id, channel, channel_thread_id);
create index idx_agents_org on agents(org_id) where is_active = true;

-- RLS (enabled on all tables, service role key bypasses)
alter table organizations enable row level security;
alter table agents enable row level security;
alter table conversations enable row level security;
alter table messages enable row level security;

-- Seed data: Jordan's org
insert into organizations (id, name, slug)
values ('1408252a-fd36-4fd3-b527-3b2f495d7b9c', 'Jordan Bartlett', 'jb');
```

- [ ] **Step 2: Run migration in Supabase SQL Editor**

Open the Supabase dashboard, go to SQL Editor, paste the contents of `001_initial_schema.sql`, and run it.

- [ ] **Step 3: Verify tables exist**

In the Supabase dashboard Table Editor, confirm these tables exist: `organizations`, `agents`, `conversations`, `messages`. Confirm the `organizations` table has one row with slug `jb`.

- [ ] **Step 4: Commit**

```bash
git add jordan-claw/supabase/
git commit -m "feat: add initial database schema migration"
```

---

### Task 4: Supabase Client and DB Layer

**Files:**
- Create: `jordan-claw/src/jordan_claw/db/__init__.py`
- Create: `jordan-claw/src/jordan_claw/db/client.py`
- Create: `jordan-claw/src/jordan_claw/db/conversations.py`
- Create: `jordan-claw/src/jordan_claw/db/messages.py`

- [ ] **Step 1: Create db package init**

`jordan-claw/src/jordan_claw/db/__init__.py`:
```python
from __future__ import annotations
```

- [ ] **Step 2: Create async Supabase client singleton**

`jordan-claw/src/jordan_claw/db/client.py`:
```python
from __future__ import annotations

from supabase._async.client import AsyncClient, create_client

_client: AsyncClient | None = None


async def get_supabase_client(url: str, service_key: str) -> AsyncClient:
    """Get or create the async Supabase client singleton."""
    global _client
    if _client is None:
        _client = await create_client(url, service_key)
    return _client


async def close_supabase_client() -> None:
    """Close the Supabase client connection."""
    global _client
    if _client is not None:
        _client = None
```

- [ ] **Step 3: Create conversations CRUD**

`jordan-claw/src/jordan_claw/db/conversations.py`:
```python
from __future__ import annotations

from supabase._async.client import AsyncClient


async def get_or_create_conversation(
    client: AsyncClient,
    org_id: str,
    channel: str,
    channel_thread_id: str,
) -> dict:
    """Find an active conversation or create a new one."""
    result = (
        await client.table("conversations")
        .select("*")
        .eq("org_id", org_id)
        .eq("channel", channel)
        .eq("channel_thread_id", channel_thread_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )

    if result.data:
        return result.data

    result = (
        await client.table("conversations")
        .insert(
            {
                "org_id": org_id,
                "channel": channel,
                "channel_thread_id": channel_thread_id,
            }
        )
        .execute()
    )
    return result.data[0]


async def update_conversation_status(
    client: AsyncClient,
    conversation_id: str,
    status: str,
) -> None:
    """Update a conversation's status."""
    await (
        client.table("conversations")
        .update({"status": status})
        .eq("id", conversation_id)
        .execute()
    )
```

- [ ] **Step 4: Create messages CRUD**

`jordan-claw/src/jordan_claw/db/messages.py`:
```python
from __future__ import annotations

from supabase._async.client import AsyncClient


async def message_exists(client: AsyncClient, channel_message_id: str) -> bool:
    """Check if a message with this channel_message_id already exists (dedup)."""
    result = (
        await client.table("messages")
        .select("id")
        .eq("channel_message_id", channel_message_id)
        .maybe_single()
        .execute()
    )
    return result.data is not None


async def save_message(
    client: AsyncClient,
    conversation_id: str,
    role: str,
    content: str,
    channel_message_id: str | None = None,
    token_count: int | None = None,
    model: str | None = None,
    cost_usd: float | None = None,
    metadata: dict | None = None,
) -> dict:
    """Save a message to the messages table."""
    data: dict = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
    }
    if channel_message_id is not None:
        data["channel_message_id"] = channel_message_id
    if token_count is not None:
        data["token_count"] = token_count
    if model is not None:
        data["model"] = model
    if cost_usd is not None:
        data["cost_usd"] = float(cost_usd)
    if metadata is not None:
        data["metadata"] = metadata

    result = await client.table("messages").insert(data).execute()
    return result.data[0]


async def get_recent_messages(
    client: AsyncClient,
    conversation_id: str,
    limit: int = 50,
) -> list[dict]:
    """Get the most recent messages for a conversation, ordered oldest first."""
    result = (
        await client.table("messages")
        .select("role, content, created_at, token_count, model, metadata")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return result.data
```

- [ ] **Step 5: Commit**

```bash
git add jordan-claw/src/jordan_claw/db/
git commit -m "feat: add Supabase async client and DB layer"
```

---

### Task 5: Gateway Models

**Files:**
- Create: `jordan-claw/src/jordan_claw/gateway/__init__.py`
- Create: `jordan-claw/src/jordan_claw/gateway/models.py`

- [ ] **Step 1: Create gateway package init**

`jordan-claw/src/jordan_claw/gateway/__init__.py`:
```python
from __future__ import annotations
```

- [ ] **Step 2: Create channel-agnostic models**

`jordan-claw/src/jordan_claw/gateway/models.py`:
```python
from __future__ import annotations

from pydantic import BaseModel


class IncomingMessage(BaseModel):
    """Channel-agnostic inbound message. Every adapter produces this."""

    channel: str
    channel_thread_id: str
    channel_message_id: str
    content: str
    org_id: str


class GatewayResponse(BaseModel):
    """Channel-agnostic response. Gateway returns this to every adapter."""

    content: str
    conversation_id: str
    token_count: int | None = None
    model: str | None = None
```

- [ ] **Step 3: Commit**

```bash
git add jordan-claw/src/jordan_claw/gateway/
git commit -m "feat: add channel-agnostic gateway models"
```

---

### Task 6: Token Counting Utility

**Files:**
- Create: `jordan-claw/src/jordan_claw/utils/__init__.py`
- Create: `jordan-claw/src/jordan_claw/utils/token_counting.py`

- [ ] **Step 1: Create utils package init**

`jordan-claw/src/jordan_claw/utils/__init__.py`:
```python
from __future__ import annotations
```

- [ ] **Step 2: Create token counting utility**

`jordan-claw/src/jordan_claw/utils/token_counting.py`:
```python
from __future__ import annotations

from pydantic_ai import RunUsage


def extract_usage(usage: RunUsage) -> dict:
    """Extract token counts from a Pydantic AI RunUsage object."""
    return {
        "input_tokens": usage.input_tokens or 0,
        "output_tokens": usage.output_tokens or 0,
        "total_tokens": (usage.input_tokens or 0) + (usage.output_tokens or 0),
        "requests": usage.requests or 0,
    }
```

- [ ] **Step 3: Commit**

```bash
git add jordan-claw/src/jordan_claw/utils/
git commit -m "feat: add token counting utility"
```

---

### Task 7: Agent Tools

**Files:**
- Create: `jordan-claw/src/jordan_claw/tools/__init__.py`
- Create: `jordan-claw/src/jordan_claw/tools/time.py`
- Create: `jordan-claw/src/jordan_claw/tools/web_search.py`

- [ ] **Step 1: Create tools package init**

`jordan-claw/src/jordan_claw/tools/__init__.py`:
```python
from __future__ import annotations
```

- [ ] **Step 2: Create current datetime tool**

`jordan-claw/src/jordan_claw/tools/time.py`:
```python
from __future__ import annotations

from datetime import UTC, datetime


def get_current_datetime() -> str:
    """Get the current date and time in UTC."""
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%d %H:%M:%S UTC (%A)")
```

- [ ] **Step 3: Create Tavily web search tool**

`jordan-claw/src/jordan_claw/tools/web_search.py`:
```python
from __future__ import annotations

from tavily import AsyncTavilyClient


async def web_search(query: str, *, api_key: str, max_results: int = 3) -> str:
    """Search the web using Tavily and return a formatted summary."""
    client = AsyncTavilyClient(api_key=api_key)
    response = await client.search(query=query, max_results=max_results)

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

- [ ] **Step 4: Commit**

```bash
git add jordan-claw/src/jordan_claw/tools/
git commit -m "feat: add datetime and Tavily web search tools"
```

---

### Task 8: Agent Factory

**Files:**
- Create: `jordan-claw/src/jordan_claw/agents/__init__.py`
- Create: `jordan-claw/src/jordan_claw/agents/factory.py`

- [ ] **Step 1: Create agents package init**

`jordan-claw/src/jordan_claw/agents/__init__.py`:
```python
from __future__ import annotations
```

- [ ] **Step 2: Create agent factory**

`jordan-claw/src/jordan_claw/agents/factory.py`:
```python
from __future__ import annotations

from pydantic_ai import Agent, ModelRequest, ModelResponse, TextPart, UserPromptPart

from jordan_claw.tools.time import get_current_datetime
from jordan_claw.tools.web_search import web_search

SYSTEM_PROMPT = """\
You are a helpful AI assistant. You are knowledgeable, concise, and direct.
You have access to tools for checking the current time and searching the web.
Use them when the user's question would benefit from real-time information.
Keep responses focused and practical.\
"""


def create_agent(*, tavily_api_key: str) -> Agent:
    """Create the Phase 1 hardcoded Pydantic AI agent."""
    agent = Agent(
        "anthropic:claude-sonnet-4-20250514",
        system_prompt=SYSTEM_PROMPT,
    )

    @agent.tool_plain
    def current_datetime() -> str:
        """Get the current date and time in UTC."""
        return get_current_datetime()

    @agent.tool_plain
    async def search_web(query: str) -> str:
        """Search the web for current information. Use for questions about recent events, facts, or anything that benefits from up-to-date data."""
        return await web_search(query, api_key=tavily_api_key)

    return agent


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

- [ ] **Step 3: Commit**

```bash
git add jordan-claw/src/jordan_claw/agents/
git commit -m "feat: add agent factory and message history conversion"
```

---

### Task 9: Gateway Router

**Files:**
- Create: `jordan-claw/src/jordan_claw/gateway/router.py`

- [ ] **Step 1: Create the gateway router**

`jordan-claw/src/jordan_claw/gateway/router.py`:
```python
from __future__ import annotations

import time

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.agents.factory import create_agent, db_messages_to_history
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
    tavily_api_key: str,
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
    log = log.bind(conversation_id=conversation_id, agent_id="claw-main")

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

    # 5-7. Build agent, convert history, run
    try:
        start = time.monotonic()
        agent = create_agent(tavily_api_key=tavily_api_key)
        history = db_messages_to_history(db_messages)

        result = await agent.run(msg.content, message_history=history)

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

    # 8. Save assistant response
    await save_message(
        db,
        conversation_id=conversation_id,
        role="assistant",
        content=response_text,
        token_count=usage["total_tokens"],
        model=model_name,
    )

    # 9. Return
    return GatewayResponse(
        content=response_text,
        conversation_id=conversation_id,
        token_count=usage["total_tokens"],
        model=model_name,
    )
```

- [ ] **Step 2: Commit**

```bash
git add jordan-claw/src/jordan_claw/gateway/router.py
git commit -m "feat: add gateway router with full message lifecycle"
```

---

### Task 10: Telegram Adapter

**Files:**
- Create: `jordan-claw/src/jordan_claw/channels/__init__.py`
- Create: `jordan-claw/src/jordan_claw/channels/telegram.py`

- [ ] **Step 1: Create channels package init**

`jordan-claw/src/jordan_claw/channels/__init__.py`:
```python
from __future__ import annotations
```

- [ ] **Step 2: Create Telegram adapter**

`jordan-claw/src/jordan_claw/channels/telegram.py`:
```python
from __future__ import annotations

import structlog
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from supabase._async.client import AsyncClient

from jordan_claw.gateway.models import IncomingMessage
from jordan_claw.gateway.router import handle_message

logger = structlog.get_logger()


def create_telegram_dispatcher(
    bot: Bot,
    *,
    db: AsyncClient,
    default_org_id: str,
    tavily_api_key: str,
    history_limit: int,
    environment: str,
) -> Dispatcher:
    """Create and configure the aiogram dispatcher with message handlers."""
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def handle_start(message: types.Message) -> None:
        await message.answer(
            "Hello! I'm your AI assistant. Send me a message and I'll do my best to help."
        )

    @dp.message()
    async def handle_text(message: types.Message) -> None:
        if not message.text:
            return

        chat_id = str(message.chat.id)
        message_id = str(message.message_id)

        incoming = IncomingMessage(
            channel="telegram",
            channel_thread_id=chat_id,
            channel_message_id=f"telegram:{message_id}",
            content=message.text,
            org_id=default_org_id,
        )

        try:
            response = await handle_message(
                incoming,
                db=db,
                tavily_api_key=tavily_api_key,
                history_limit=history_limit,
                environment=environment,
            )

            if response.content:
                await message.answer(response.content)

        except Exception:
            logger.exception(
                "telegram_handler_error", chat_id=chat_id, message_id=message_id
            )
            await message.answer("Something went wrong. Try again.")

    return dp


async def start_polling(bot: Bot, dp: Dispatcher) -> None:
    """Start aiogram long-polling. Runs until cancelled."""
    logger.info("telegram_polling_started")
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("telegram_polling_stopped")
```

- [ ] **Step 3: Commit**

```bash
git add jordan-claw/src/jordan_claw/channels/
git commit -m "feat: add Telegram adapter with aiogram long-polling"
```

---

### Task 11: FastAPI App and Lifespan

**Files:**
- Create: `jordan-claw/src/jordan_claw/main.py`

- [ ] **Step 1: Create the FastAPI app with lifespan, logging, and health check**

`jordan-claw/src/jordan_claw/main.py`:
```python
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import structlog
from aiogram import Bot
from fastapi import FastAPI

from jordan_claw.channels.telegram import create_telegram_dispatcher, start_polling
from jordan_claw.config import get_settings
from jordan_claw.db.client import close_supabase_client, get_supabase_client


def configure_logging(environment: str, log_level: str) -> None:
    """Configure structlog with console (dev) or JSON (prod) rendering."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if environment == "production":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.environment, settings.log_level)
    logger = structlog.get_logger()

    # Initialize Supabase client
    db = await get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    logger.info("supabase_client_initialized")

    # Initialize Telegram bot and dispatcher
    bot = Bot(token=settings.telegram_bot_token)
    dp = create_telegram_dispatcher(
        bot,
        db=db,
        default_org_id=settings.default_org_id,
        tavily_api_key=settings.tavily_api_key,
        history_limit=settings.message_history_limit,
        environment=settings.environment,
    )

    # Start Telegram polling as background task
    polling_task = asyncio.create_task(start_polling(bot, dp))
    logger.info("application_started", environment=settings.environment)

    yield

    # Shutdown
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    await bot.session.close()
    await close_supabase_client()
    logger.info("application_stopped")


app = FastAPI(title="Jordan Claw", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

- [ ] **Step 2: Verify the app starts locally**

```bash
cd jordan-claw && infisical run -- uv run uvicorn jordan_claw.main:app --host 0.0.0.0 --port 8000
```

Expected: App starts, structlog output shows `supabase_client_initialized`, `telegram_polling_started`, `application_started`. The `/health` endpoint returns `{"status": "ok"}` at `http://localhost:8000/health`.

- [ ] **Step 3: Commit**

```bash
git add jordan-claw/src/jordan_claw/main.py
git commit -m "feat: add FastAPI app with lifespan, logging, and health check"
```

---

### Task 12: Gateway Router Tests

**Files:**
- Create: `jordan-claw/tests/test_gateway.py`

- [ ] **Step 1: Write tests for the gateway router**

`jordan-claw/tests/test_gateway.py`:
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
    with patch(
        "jordan_claw.gateway.router.message_exists", return_value=True
    ):
        result = await handle_message(
            make_incoming(),
            db=mock_db,
            tavily_api_key="test-key",
        )

    assert result.content == ""
    assert result.conversation_id == ""


@pytest.mark.asyncio
async def test_successful_message_flow(mock_db):
    """A normal message should go through the full lifecycle and return a response."""
    fake_conversation = {"id": "conv-001"}
    fake_messages = [
        {"role": "user", "content": "Hi", "created_at": "2026-01-01T00:00:00Z",
         "token_count": None, "model": None, "metadata": {}},
    ]

    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_usage.requests = 1

    mock_result = MagicMock()
    mock_result.output = "Hello! How can I help?"
    mock_result.usage.return_value = mock_usage

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
            "jordan_claw.gateway.router.create_agent",
        ) as mock_create_agent,
    ):
        mock_agent = AsyncMock()
        mock_agent.run.return_value = mock_result
        mock_create_agent.return_value = mock_agent

        result = await handle_message(
            make_incoming(),
            db=mock_db,
            tavily_api_key="test-key",
        )

    assert result.content == "Hello! How can I help?"
    assert result.conversation_id == "conv-001"
    assert result.token_count == 15
    assert result.model == "claude-sonnet-4-20250514"


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
            "jordan_claw.gateway.router.create_agent",
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
            tavily_api_key="test-key",
        )

    assert result.content == ERROR_RESPONSE
    assert result.conversation_id == "conv-002"
```

- [ ] **Step 2: Run the tests**

```bash
cd jordan-claw && uv run pytest tests/test_gateway.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 3: Fix any failures, re-run until green**

- [ ] **Step 4: Commit**

```bash
git add jordan-claw/tests/
git commit -m "test: add gateway router unit tests"
```

---

### Task 13: Message History Conversion Tests

**Files:**
- Create: `jordan-claw/tests/test_agents.py`

- [ ] **Step 1: Write tests for message history conversion**

`jordan-claw/tests/test_agents.py`:
```python
from __future__ import annotations

from pydantic_ai import ModelRequest, ModelResponse, TextPart, UserPromptPart

from jordan_claw.agents.factory import db_messages_to_history


def test_empty_history():
    result = db_messages_to_history([])
    assert result == []


def test_user_and_assistant_messages():
    db_rows = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "What time is it?"},
    ]
    result = db_messages_to_history(db_rows)

    assert len(result) == 3
    assert isinstance(result[0], ModelRequest)
    assert result[0].parts[0].content == "Hello"
    assert isinstance(result[1], ModelResponse)
    assert result[1].parts[0].content == "Hi there!"
    assert isinstance(result[2], ModelRequest)


def test_system_and_tool_roles_skipped():
    db_rows = [
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": "Hello"},
        {"role": "tool", "content": "tool output"},
        {"role": "assistant", "content": "Hi"},
    ]
    result = db_messages_to_history(db_rows)

    assert len(result) == 2
    assert isinstance(result[0], ModelRequest)
    assert isinstance(result[1], ModelResponse)
```

- [ ] **Step 2: Run the tests**

```bash
cd jordan-claw && uv run pytest tests/test_agents.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 3: Commit**

```bash
git add jordan-claw/tests/test_agents.py
git commit -m "test: add message history conversion tests"
```

---

### Task 14: Dockerfile and Deployment Config

**Files:**
- Create: `jordan-claw/Dockerfile`

- [ ] **Step 1: Create the Dockerfile**

`jordan-claw/Dockerfile`:
```dockerfile
FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Install dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

# Copy application code
COPY src/ src/

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "jordan_claw.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Verify Docker build succeeds**

```bash
cd jordan-claw && docker build -t jordan-claw:test .
```

Expected: Build completes without errors.

- [ ] **Step 3: Commit**

```bash
git add jordan-claw/Dockerfile
git commit -m "chore: add Dockerfile for Railway deployment"
```

---

### Task 15: Lint, Format, Final Verification

**Files:**
- Modify: all `.py` files (if ruff fixes anything)

- [ ] **Step 1: Run ruff format**

```bash
cd jordan-claw && uv run ruff format src/ tests/
```

- [ ] **Step 2: Run ruff check with auto-fix**

```bash
cd jordan-claw && uv run ruff check src/ tests/ --fix
```

Expected: No errors, or only auto-fixable ones.

- [ ] **Step 3: Run full test suite**

```bash
cd jordan-claw && uv run pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit any formatting fixes**

```bash
git add -A jordan-claw/
git commit -m "chore: apply ruff formatting and lint fixes"
```

(Skip this commit if no changes were made.)

---

### Task 16: End-to-End Smoke Test

**Files:** None (manual verification)

- [ ] **Step 1: Add DEFAULT_ORG_ID to Infisical**

```bash
infisical secrets set DEFAULT_ORG_ID=1408252a-fd36-4fd3-b527-3b2f495d7b9c
```

- [ ] **Step 2: Start the application locally**

```bash
cd jordan-claw && infisical run -- uv run uvicorn jordan_claw.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 3: Verify health endpoint**

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: Send a message via Telegram**

Open Telegram, find the bot, send `/start`. Then send "What time is it?" Verify:
- Bot responds with the current time
- Bot responds within a few seconds
- Sending a follow-up message shows the bot has context from the previous message

- [ ] **Step 5: Verify data in Supabase**

In the Supabase dashboard, check:
- `conversations` table has a new row with `channel=telegram`
- `messages` table has both user and assistant messages
- Assistant messages have `token_count` and `model` populated

- [ ] **Step 6: Commit any fixes needed**

If any issues were found and fixed during smoke testing, commit them individually with descriptive messages.
