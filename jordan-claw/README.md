# Jordan Claw

A multi-tenant AI agent gateway. Receives messages from Telegram, routes them to a Pydantic AI agent, persists conversations in Supabase, and returns responses.

This is the core delivery engine for the [jordanbartlett.co](https://jordanbartlett.co) consultancy. Every future client engagement builds on this infrastructure.

## What It Does

One deployed process. One agent today, many tomorrow. Messages come in from Telegram, hit a gateway that handles dedup, conversation tracking, and history, then run through a Pydantic AI agent backed by Claude Sonnet 4.

The agent ("claw-main") currently has four tools:

- **current_datetime** returns the current time in US Central
- **search_web** searches the web via Tavily and summarizes results
- **check_calendar** reads events from a Fastmail calendar via CalDAV
- **schedule_event** creates events on that same calendar

Conversations and messages persist in Supabase. The schema is multi-tenant from day one.

## Stack

| Layer | Technology |
|-------|-----------|
| Gateway | FastAPI |
| Agent framework | Pydantic AI |
| Persistence | Supabase (Postgres) |
| Telegram | aiogram (long-polling) |
| Calendar | CalDAV via `caldav` library |
| LLM | Claude Sonnet 4 (Anthropic) |
| Web search | Tavily |
| Deployment | Railway |

## Project Structure

```
jordan-claw/
  src/jordan_claw/
    main.py              # FastAPI app, lifespan, logging
    config.py            # pydantic-settings, env vars
    agents/
      factory.py         # Agent creation, system prompt, tool registration
    channels/
      telegram.py        # aiogram adapter
    gateway/
      models.py          # IncomingMessage, GatewayResponse
      router.py          # Message lifecycle: dedup, history, agent run, persist
    tools/
      calendar.py        # Fastmail CalDAV client
      time.py            # Central time
      web_search.py      # Tavily search
    db/
      client.py          # Async Supabase client
      conversations.py   # Conversation CRUD
      messages.py        # Message CRUD
    utils/
      token_counting.py  # Extract token counts from agent results
  tests/
  supabase/migrations/
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

Four tables in Supabase:

- **organizations** stores tenants (one today: Jordan Bartlett)
- **agents** stores agent config (one today: claw-main). The code doesn't read from this table yet. It will in Phase 2.
- **conversations** tracks threads keyed by org + channel + thread ID
- **messages** stores every message with role, content, token count, model, and cost

RLS is enabled on all tables. Phase 1 uses the service role key (server-side only).

## What's Next

- **Find availability**: "Find me a time this week to meet with Sarah"
- **Tool registry from DB**: Agents and tools configured in Supabase instead of hardcoded
- **Slack adapter**: Second channel
- **Sub-agent delegation**: Specialized agents for specific tasks
- **Knowledge base**: Vector search over documents

## Docs

- `jordan-claw-prd.md` in the repo root has the full product spec with architecture and phased roadmap
- `docs/superpowers/specs/` has design specs
- `docs/superpowers/plans/` has implementation plans
