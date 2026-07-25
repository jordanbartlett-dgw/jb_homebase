# Jordan Claw

A multi-tenant AI agent gateway. Receives messages from Telegram, routes them to a Pydantic AI agent, persists conversations in Supabase, and returns responses.

This is the core delivery engine for the [jordanbartlett.co](https://jordanbartlett.co) consultancy. Every future client engagement builds on this infrastructure.

## What It Does

One deployed process, two agents. Messages arrive from Telegram (one bot per agent), inbound webhooks, a Fastmail email watcher, or the `/voice` endpoint, hit a gateway that handles dedup, conversation tracking, and history, then run through a Pydantic AI (v2) agent backed by Claude Sonnet 5.

Tools are grouped into six capability bundles (`core`, `web`, `calendar`, `memory`, `obsidian`, `workout` in `agents/capabilities.py`); each agent's DB config selects which bundles it gets. The sixteen tools:

- **current_datetime** returns the current time in US Central
- **search_web** searches the web via Tavily for external discovery (default when unsure)
- **check_calendar** / **schedule_event** reads and creates Fastmail calendar events via CalDAV
- **recall_memory** / **forget_memory** queries and manages persistent memory facts
- **search_notes** / **read_note** semantic search over Obsidian vault notes via pgvector (personal notes only)
- **create_source_note** / **fetch_article** creates source notes from URLs or manual input
- **get_workout_profile** / **save_workout_profile** / **get_workout_plan** / **save_workout_plan** / **log_workout** / **get_recent_workouts** back the workout-coach agent

A second agent ("workout-coach") runs on its own Telegram bot (enabled via `WORKOUT_TELEGRAM_BOT_TOKEN`): structured intake of training/nutrition preferences, persisted training plans, chat workout logging, and a 6am daily-workout nudge.

The agent also proactively reaches out via Telegram:

- **Morning briefing** (daily 7am) with calendar overview and memory context
- **Weekly review** (Mondays 8am) summarizing the week's events and learnings
- **Calendar reminders** 30 minutes before meetings with attendee context
- **Memory corrections** notifies when a remembered fact is updated
- **Daily scan** alerts on calendar conflicts (quiet, only messages if something found)
- **Weekly feedback request** (Sundays 7pm Central) asks for a 1-5 rating on the week's interactions, persisted via `/feedback`
- **Daily workout** (6am Central) sends the day's session from the active training plan; silent on rest days

Beyond schedules, events can trigger agents:

- **`POST /webhooks/{source}`** (shared-secret auth) matches DB-configured `event_triggers` rows, runs the target agent, and delivers via Telegram; agents reply `NOTHING_TO_SEND` to stay silent on noise
- **Fastmail watcher** polls JMAP every 5 minutes and feeds new email through the same trigger pipeline (seeded: `inbound_email_review` triages inbound mail)
- **`POST /voice`** (bearer auth) accepts raw audio, transcribes via Whisper, routes to the best-matching agent with a Haiku classifier built from the capability catalog, and returns transcript + reply. Replays are idempotent: send one `X-Idempotency-Key` per utterance (falls back to a body hash) and duplicates converge to the original reply.

Conversation history is token-budgeted (4000 tokens max) to prevent context pollution on long conversations. Tool docstrings include explicit routing signals so the LLM knows when to use internal tools (notes, memory, calendar) vs external tools (web search). Conversations auto-expire after 30 minutes of inactivity, so unrelated prior topics don't bleed into new sessions.

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
      __init__.py        # BASE_TOOLSET (FunctionToolset) with all agent tools
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
      usage_events.py    # Per-run analytics rows + most_recent_agent helper
      feedback.py        # Feedback table CRUD
    analytics/
      types.py           # RunKind StrEnum, AgentRunResult dataclass
      posthog_client.py  # PostHog client factory + shutdown
      emitter.py         # Fire-and-forget event emit + drain_pending_emits
    utils/
      token_counting.py  # Extract token counts from agent results
      pricing.py         # Claude price table + compute_cost
      agent_runner.py    # Shared instrumented wrapper around agent.run()
evals/                   # Top-level (not under tests/) — eval runs cost money
  registry.py            # EvalSpec registry binding YAML to task fns and scorers
  run_eval.py            # claw-eval CLI: run, --all, --save-baseline
  datasets/              # memory_recall.yaml, obsidian_retrieval.yaml (20 cases each)
  scorers/               # RequiredFactsScorer, TopKMembershipScorer + LLMJudge config
  tasks/                 # memory_recall_task, obsidian_retrieval_task
  fixtures/corpus.yaml   # 30-note synthetic eval corpus
  baselines/             # Committed score baselines for regression detection
tests/                   # 307 unit and integration tests
scripts/
  obsidian_sync/         # CLI for vault ingest/export
supabase/migrations/     # 001-014 schema migrations (005 removed as a no-op)
docs/plans/              # Implementation plans (Flutter PRD, locked decisions)
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
CI (GitHub Actions) runs ruff lint, a format gate, and the full test suite
on every push and pull request.

```
Repo:   jordanbartlett-dgw/jb_homebase
Bot:    @jb_homebase_bot
Health: GET /health -> config-aware report (active agents vs running bots,
        DB models validated against the Anthropic models API); degraded -> 503.
        Railway healthchecks this path on deploy, so a broken config never
        replaces a healthy deployment.
Port:   8000
```

## Database

Sixteen tables in Supabase:

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
- **usage_events** one row per agent run — cost, tokens, latency, outcome (source of truth for cost / quality dashboards)
- **feedback** rating + optional note per `/feedback` submission, attributed to the most recent agent
- **workout_profiles** / **workout_plans** / **workout_logs** training preferences, one-active-per-org plans, and logged workouts for the workout coach

RLS is enabled on all tables. Uses the service role key (server-side only).

## Observability

Every agent run goes through `src/jordan_claw/utils/agent_runner.py:run_agent_instrumented`, which produces four signals:

1. **Logfire trace** — parent `agent run` span carrying `agent_slug`, `channel`, `run_kind`, `usage.cost_usd`, `usage.duration_ms`, `usage.tool_call_count`, `outcome.success`. Auto-instrumentation via `logfire.instrument_pydantic_ai()` populates the child `chat anthropic:*` spans.
2. **`usage_events` row** — fire-and-forget INSERT for queryable analytics (`run_kind` ∈ `user_message` / `proactive` / `memory_extract` / `eval`).
3. **PostHog `agent_run_completed` event** — feeds the production dashboard (id `1543058`) with cost, latency, runs-per-agent, and feedback rollups.
4. **Token-budget guardrail** — runs that exceed 200K total tokens raise `TokenBudgetExceededError` and record a failure row instead of melting the bill.

A separate Railway service (`evals-cron`) runs the Pydantic Evals suite nightly at 03:00 UTC against `memory_recall` and `obsidian_retrieval` datasets. Baselines are committed; >5pp drops exit non-zero and emit a regression event. See `docs/evals.md` for the harness and `docs/observability.md` for the run-time signal map. `POST /api/analytics/event` is mounted as a frontend proxy for future client-side emissions.

## What's Next

- **Flutter app**: Replace Telegram as Jordan's primary channel (upcoming)
- **Slack adapter**: Second channel
- **Sub-agent delegation**: Specialized agents for specific tasks
- **Multi-agent routing**: Route conversations to the right agent per org

## Docs

- `docs/observability.md` — Logfire / `usage_events` / PostHog signal map
- `docs/evals.md` — Pydantic Evals harness and dataset authoring guide
- `docs/claw-main-prompt-reference.md` — agent prompt reference
- `docs/jordan-claw-lessons-learned.md` — retrospective notes
- `docs/superpowers/specs/` — older design specs
- `docs/superpowers/plans/` — older implementation plans
