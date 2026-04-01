# Jordan Claw Phase 1 Design Spec

**Date:** 2026-04-01
**Status:** Approved
**Owner:** Jordan Bartlett

## Overview

Jordan Claw Phase 1 is the MVP: a single FastAPI process that runs an aiogram Telegram bot, routes messages through a Pydantic AI agent, and persists conversations in Supabase. One org, one agent, two tools, deployed to Railway.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Process model | Single process (FastAPI + aiogram) | One user, one channel. No reason to split. |
| Gateway pattern | Direct function call (Approach A) | No HTTP overhead. Channel-agnostic models prep for Approach B later. |
| Auth | Skipped for Phase 1 | No auth.users dependency. user_id nullable. org_members table omitted. |
| Tools | Current datetime + Tavily web search | Two tools, useful for general assistant use. |
| Logging | structlog, console (dev) / JSON (prod) | Switched by environment setting. |
| Message history | 50 messages (configurable) | 25 exchanges. Plenty of room in Sonnet's 200k context. |
| Deployment | Railway, Dockerfile included from day one | Single service, auto-deploy from main. |
| Default org UUID | `1408252a-fd36-4fd3-b527-3b2f495d7b9c` | Pre-generated. Used in migration and env var. |

## Project Structure

```
jordan-claw/
  src/
    jordan_claw/
      __init__.py
      main.py                 # FastAPI app, lifespan (starts/stops aiogram)
      config.py               # Settings via pydantic-settings
      gateway/
        __init__.py
        router.py             # handle_message() core function
        models.py             # IncomingMessage, GatewayResponse
      channels/
        __init__.py
        telegram.py           # aiogram adapter
      agents/
        __init__.py
        factory.py            # Build Pydantic AI agent, message history conversion
      tools/
        __init__.py
        time.py               # Current datetime tool
        web_search.py         # Tavily search tool
      db/
        __init__.py
        client.py             # Async Supabase client singleton
        conversations.py      # Conversation CRUD
        messages.py           # Message CRUD
      utils/
        __init__.py
        token_counting.py     # Extract token counts from agent result
  tests/
    __init__.py
    test_gateway.py
  pyproject.toml
  Dockerfile
  .env.example
```

## Config

```python
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
```

## Database Schema

### Tables

**organizations** - single row for Phase 1.

```sql
create table organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    slug text unique not null,
    settings jsonb default '{}',
    created_at timestamptz default now()
);
```

**agents** - exists in schema for Phase 2. Not read by Phase 1 code.

```sql
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
```

**conversations** - user_id nullable, no auth.users reference.

```sql
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
```

**messages** - stores every message with role, content, token count, model.

```sql
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
```

### Indexes

```sql
create index idx_messages_conversation_created on messages(conversation_id, created_at);
create index idx_messages_channel_dedup on messages(channel_message_id) where channel_message_id is not null;
create index idx_conversations_channel on conversations(org_id, channel, channel_thread_id);
create index idx_agents_org on agents(org_id) where is_active = true;
```

### RLS

RLS enabled on all tables. Service role key bypasses RLS in Phase 1. Policies applied from the start for Phase 4 readiness.

### Seed Data

```sql
INSERT INTO organizations (id, name, slug)
VALUES ('1408252a-fd36-4fd3-b527-3b2f495d7b9c', 'Jordan Bartlett', 'jb');
```

## Gateway Router

`handle_message(msg: IncomingMessage) -> GatewayResponse`

### Models

```python
class IncomingMessage(BaseModel):
    channel: str                    # "telegram", "slack", "web", "api"
    channel_thread_id: str          # chat_id, thread_ts, session_id
    channel_message_id: str         # for dedup
    content: str
    org_id: str

class GatewayResponse(BaseModel):
    content: str
    conversation_id: str
    token_count: int | None = None
    model: str | None = None
```

### Message Lifecycle

1. Dedup check via `channel_message_id`. Return early if exists.
2. Get or create conversation by `(org_id, channel, channel_thread_id)`.
3. Save user message to messages table.
4. Load last 50 messages for this conversation.
5. Build agent via `factory.create_agent()`.
6. Convert DB messages to Pydantic AI `ModelMessage` format.
7. Run agent with message history.
8. Save assistant response with token count and model.
9. Return `GatewayResponse`.

### Error Handling

Steps 5-8 wrapped in try/except. On failure: log error with full context, save error indicator, set conversation status to `error`, return user-friendly error string. Gateway never throws to the channel adapter.

## Agent

### Configuration (hardcoded Phase 1)

- **Model:** `claude-sonnet-4-20250514`
- **System prompt:** Short general assistant prompt. Placeholder name (not "Claw", to be tuned later).
- **Tools:** current datetime, Tavily web search

Agent instance created once at startup and reused (stateless, conversation state passed via message_history).

### Message History Conversion

DB rows converted to Pydantic AI `ModelMessage` types:
- `user` role -> `ModelRequest` with `UserPromptPart`
- `assistant` role -> `ModelResponse` with `TextPart`
- `system` and `tool` roles skipped in Phase 1

### Tools

**`tools/time.py`** - returns current datetime with timezone. No external calls.

**`tools/web_search.py`** - wraps async Tavily client. Takes a query, returns formatted summary of top 3-5 results. Tavily API key from settings.

## Telegram Adapter

- aiogram 3.x, long-polling mode via `Dispatcher.start_polling()`
- Single message handler for text messages
- Extracts `chat_id`, `message_id`, `text` from update
- Builds `IncomingMessage` with `channel="telegram"`, `channel_thread_id=str(chat_id)`, `channel_message_id=str(message_id)`, `org_id=settings.default_org_id`
- Calls `handle_message()` directly (no HTTP)
- Sends `GatewayResponse.content` back to same `chat_id`
- On error: sends "Something went wrong. Try again." to user, logs full traceback

### Lifecycle

FastAPI lifespan starts aiogram polling as a background asyncio task. Shutdown cancels the task gracefully.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    polling_task = asyncio.create_task(start_telegram_polling())
    yield
    polling_task.cancel()
```

## Logging

- structlog configured at startup
- Console renderer for `environment == "development"`, JSON renderer for `environment == "production"`
- Every agent run logs: `org_id`, `conversation_id`, `agent_id`, `channel`, `input_tokens`, `output_tokens`, `total_tokens`, `model`, `latency_ms`, `status`
- Message content only logged in development
- Errors logged with full traceback and correlation context

## Deployment

### Dockerfile

Python 3.12 slim base. uv for package management. Deps cached in separate layer. Runs uvicorn on port 8000.

### Railway

- Single service, auto-deploys from main branch
- Env vars set in Railway dashboard (from Infisical)
- Health check: HTTP GET `/health` returns `{"status": "ok"}`
- Port: 8000

### Local Dev

```bash
infisical run -- uv run uvicorn jordan_claw.main:app --reload
```

### .env.example

```
ANTHROPIC_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_ANON_KEY=
TELEGRAM_BOT_TOKEN=
TAVILY_API_KEY=
DEFAULT_ORG_ID=
```

## Out of Scope (Phase 1)

- Slack adapter
- Web/API channel
- Sub-agent delegation
- Tool registry from DB
- Knowledge base / vector search
- Org secrets encryption
- Cost tracking / billing
- Proactive messaging
- org_members table
- auth.users integration
