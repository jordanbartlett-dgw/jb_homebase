# Jordan Claw

A multi-tenant AI agent gateway. Receives messages from Telegram, routes them to a Pydantic AI agent, persists conversations in Supabase, and returns responses.

This is the core delivery engine for the [jordanbartlett.co](https://jordanbartlett.co) consultancy. Every future client engagement builds on this infrastructure.

## What It Does

One deployed process. One agent today, many tomorrow. Messages come in from Telegram, hit a gateway that handles dedup, conversation tracking, and history, then run through a Pydantic AI agent backed by Claude Sonnet 4.

The agent ("claw-main") has ten tools:

- **current_datetime** returns the current time in US Central
- **search_web** searches the web via Tavily and summarizes results
- **check_calendar** / **schedule_event** reads and creates Fastmail calendar events via CalDAV
- **recall_memory** / **forget_memory** queries and manages persistent memory facts
- **search_notes** / **read_note** semantic search over Obsidian vault notes via pgvector
- **create_source_note** / **fetch_article** creates source notes from URLs or manual input

The agent also proactively reaches out via Telegram:

- **Morning briefing** (daily 7am) with calendar overview and memory context
- **Weekly review** (Mondays 8am) summarizing the week's events and learnings
- **Calendar reminders** 30 minutes before meetings with attendee context
- **Memory corrections** notifies when a remembered fact is updated
- **Daily scan** alerts on calendar conflicts (quiet, only messages if something found)

Conversations and messages persist in Supabase. The schema is multi-tenant from day one.

## Stack

| Layer | Technology |
|-------|-----------|
| Gateway | FastAPI |
| Agent framework | Pydantic AI |
| Persistence | Supabase (Postgres + pgvector) |
| Telegram | aiogram (long-polling) |
| Calendar | CalDAV via `caldav` library |
| LLM | Claude Sonnet 4 (Anthropic) |
| Embeddings | OpenAI text-embedding-3-small |
| Web search | Tavily |
| Scheduling | croniter (in-process async loop) |
| Deployment | Railway |

## Project Structure

```
jordan-claw/
  src/jordan_claw/
    main.py              # FastAPI app, lifespan, scheduler startup
    config.py            # pydantic-settings, env vars
    agents/
      deps.py            # AgentDeps model (credentials for tools)
      factory.py         # DB-driven agent creation, tool registry resolution
    channels/
      telegram.py        # aiogram adapter, chat ID persistence
    gateway/
      models.py          # IncomingMessage, GatewayResponse
      router.py          # Message lifecycle: dedup, history, agent run, persist
    tools/
      __init__.py        # TOOL_REGISTRY mapping names to callables
      calendar.py        # Fastmail CalDAV client
      memory.py          # recall_memory, forget_memory tools
      obsidian.py        # search_notes, read_note, create_source_note, fetch_article
      time.py            # Central time
      web_search.py      # Tavily search
    memory/
      extractor.py       # Background memory extraction via Haiku
      models.py          # ExtractedFact, ExtractionResult, MemoryFact
      reader.py          # Memory context rendering for system prompts
    obsidian/
      embeddings.py      # OpenAI embedding generation
      models.py          # ObsidianNote, ObsidianNoteChunk
      parser.py          # Frontmatter, wiki-links, content hashing
    proactive/
      scheduler.py       # Async cron loop, calendar reminder timers
      executors.py       # Morning briefing, weekly review, daily scan, reminders
      delivery.py        # Telegram send with dedup and audit logging
      models.py          # ProactiveSchedule
    db/
      client.py          # Async Supabase client
      agents.py          # Agent config queries
      conversations.py   # Conversation CRUD
      memory.py          # Memory facts, events, context CRUD
      messages.py        # Message CRUD
      obsidian.py        # Obsidian notes and chunks CRUD
      proactive.py       # Schedule and proactive message CRUD
    utils/
      token_counting.py  # Extract token counts from agent results
  tests/                 # 146 unit and integration tests
  scripts/
    obsidian_sync/       # CLI for vault ingest/export
  supabase/migrations/   # 001-004 schema migrations
  Dockerfile
  pyproject.toml
```

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Supabase project with the schema from `supabase/migrations/001_initial_schema.sql`
- Telegram bot token (via BotFather)
- Anthropic API key
- Tavily API key
- Fastmail account with an app-specific password

### Install

```bash
cd jordan-claw
uv sync --dev
```

### Configure

Copy `.env.example` to `.env` and fill in the values:

```
ANTHROPIC_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_ANON_KEY=
TELEGRAM_BOT_TOKEN=
TAVILY_API_KEY=
DEFAULT_ORG_ID=
FASTMAIL_USERNAME=your-email@fastmail.com
FASTMAIL_APP_PASSWORD=your-app-specific-password
OPENAI_API_KEY=
```

Secrets are managed via Infisical in production.

### Run locally

```bash
uv run uvicorn jordan_claw.main:app --reload
```

The Telegram bot starts automatically via long-polling. No webhook URL needed.

### Run tests

```bash
uv run pytest tests/ -v
```

Tests mock all external services. No live API calls.

## Deployment

Deployed to Railway. Auto-deploys from the `main` branch on GitHub.

```
Repo:   jordanbartlett-dgw/jb_homebase
Bot:    @jb_homebase_bot
Health: GET /health -> {"status": "ok"}
Port:   8000
```

## Database

Ten tables in Supabase:

- **organizations** stores tenants (one today: Jordan Bartlett)
- **agents** stores agent config (one today: claw-main), DB-driven tools and system prompts
- **conversations** tracks threads keyed by org + channel + thread ID
- **messages** stores every message with role, content, token count, model, and cost
- **memory_facts** persistent facts extracted from conversations
- **memory_events** notable events and corrections
- **memory_context** pre-rendered context blocks for system prompt injection
- **obsidian_notes** / **obsidian_note_chunks** vault notes with pgvector embeddings
- **proactive_schedules** cron-driven task definitions for outbound messaging
- **proactive_messages** audit log of every proactive message sent

RLS is enabled on all tables. Uses the service role key (server-side only).

## What's Next

- **Slack adapter**: Second channel
- **Sub-agent delegation**: Specialized agents for specific tasks
- **Multi-agent routing**: Route conversations to the right agent per org

## Docs

- `jordan-claw-prd.md` in the repo root has the full product spec with architecture and phased roadmap
- `docs/superpowers/specs/` has design specs
- `docs/superpowers/plans/` has implementation plans
