# Architecture — Jordan Claw / jb_homebase

Maintained system map. Update this file when flows or modules change; it is the
first thing a session reads (per CLAUDE.md). Line numbers drift — treat them as
"look here first" pointers, and trust names over numbers.

Verified against main @ 59dd470 (2026-07-07).

## One process, three inbound surfaces, one core

Everything runs in a single FastAPI process (`main.py` lifespan): both Telegram
bots (aiogram long-polling as asyncio tasks), the proactive scheduler loop, and
the HTTP routes. There is no worker service, no queue, no webhook-mode Telegram.

Every inbound message, regardless of channel, funnels into
`gateway/router.py::handle_message` — the single agent-run lifecycle.

### Message flow (Telegram)

1. `channels/telegram.py::handle_text` (aiogram catch-all) → builds `IncomingMessage`
2. `gateway/router.py::handle_message`:
   - `db/messages.py::message_exists` — dedup on `channel_message_id`
     (`telegram:{chat_id}:{message_id}`); duplicate → empty-content sentinel
   - gather: `get_or_create_conversation` + `load_memory_context` + `get_agent_config`
   - gather: `save_message`(user) + `get_recent_messages` (current msg filtered out)
   - `agents/factory.py::create_agent` → `utils/agent_runner.py::run_agent_instrumented`
   - `save_message`(assistant, with tokens/model/cost)
   - fire-and-forget `memory/extractor.py::extract_memory_background`
3. back in telegram handler: `message.answer(content, parse_mode="Markdown")`,
   plain-text fallback on parse error. Empty content → no send.

### Message flow (app + voice)

- `POST /app/messages` (`main.py::app_text_message`): bearer `CLAW_APP_TOKEN`,
  explicit `agent_slug` (no classifier), dedup key `app-{slug}-{idempotency_key}`,
  replay converges via `gateway/app_chat.py::replay_app_response`. Blocking reply
  `{agent_slug, reply, conversation_id}`. Channel `app`, one conversation per
  agent (`channel_thread_id` = slug).
- `POST /voice` (`main.py::voice_message`): raw audio body + bearer auth →
  `gateway/voice.py::transcribe` (raw httpx to OpenAI Whisper) →
  `gateway/classifier.py::classify` (Haiku, structured `RouteDecision`, always
  falls back to `claw-main`) → `gateway/voice.py::handle_app_message` → same
  `handle_message` core. Replayed request skips transcription+run and polls the
  original reply (`await_original_reply`, 2s × 90s → 504).

### Event flow (webhooks + fastmail)

- `POST /webhooks/{source}`: `X-Claw-Secret` (compare_digest; unset secret = 503)
  → fire-and-forget `events/pipeline.py::process_event` → for each enabled
  `event_triggers` row for that source: build that trigger's agent, render
  `prompt_template` against the payload (missing keys safe), run
  (`run_kind=EVENT`), deliver via `proactive/delivery.py::send_proactive_message`
  unless output is `NOTHING_TO_SEND`. Per-trigger try/except isolation.
- `events/fastmail.py::poll_fastmail`: JMAP poll on a schedule (task_type
  `fastmail_watch`), cursor in `watcher_cursors` (first poll seeds cursor, no
  backfill storm), fires `process_event(source="fastmail-email")` per new email.
  Disabled when `FASTMAIL_API_TOKEN` is empty.

### Proactive flow

`proactive/scheduler.py::scheduler_loop` wakes every 60s, evaluates each enabled
`proactive_schedules` row — cron expression (croniter, per-schedule timezone) or
one-shot `run_at` timestamp — against `last_run_at`, dispatches to `EXECUTOR_MAP`
(`proactive/executors.py`): morning_briefing, weekly_review, daily_scan,
weekly_feedback_request, calendar_reminder, daily_workout, reminder (delivers
`config.message` verbatim, no LLM), weekly_training_review (Sunday 6pm coach
review of the week's logs vs plan; deterministic one-liner when there's no plan
or no logs), plus fastmail_watch. One-shots are disabled by `dispatch_task`
after firing. Delivery is Telegram-only with same-day dedup (`was_sent_today`)
— except task_type `reminder`, which dedups on a 5-min `was_sent_within` window
so sub-daily recurring reminders can fire. Morning briefing also seeds
in-process `loop.call_later` timers for 30-min-before calendar reminders.
Schedule rows carry `source` ('system' vs 'reminder'); the reminders tools only
ever list/cancel `source='reminder'` rows.

## Agent construction

- Config source of truth: `agents` DB row (`db/agents.py::AgentConfig`) —
  `slug`, `system_prompt`, `model` (provider-prefixed, nullable), `capabilities
  text[]`, `is_active`. Two agents: `claw-main`, `workout-coach`. A NULL model
  inherits `organizations.default_model` (`db/agents.py::resolve_model` — row
  override wins); `/health` validates the RESOLVED model and degrades when
  neither is set.
- `agents/factory.py::create_agent`: `Agent(config.model, instructions=memory
  block + system_prompt, capabilities=[*resolve_capabilities(config.capabilities),
  ProcessHistory(trim_history_processor)], deps_type=AgentDeps)`.
- `agents/capabilities.py::CAPABILITY_REGISTRY` — capability id → `ToolGroup`
  (a `FunctionToolset`): **core** (current_datetime), **web** (search_web,
  fetch_article), **calendar** (check_calendar, schedule_event), **memory**
  (recall_memory, forget_memory), **obsidian** (search_notes, read_note,
  create_source_note), **workout** (7 tools), **reminders** (set_reminder,
  list_reminders, cancel_reminder), plus read-only cross-agent views
  **workout_readonly** (3 read tools, on claw-main) and **obsidian_readonly**
  (search_notes + read_note, on workout-coach) that reuse the same tool fns —
  never grant a *_readonly group alongside its full group (duplicate names).
  20 distinct tools total. Unknown ids are skipped with a warning (safe deploy
  ordering). log_workout refuses same-day same-activity duplicates unless
  allow_duplicate=true; amend_last_workout updates the latest log (follow-up
  detail was double-logging sessions).
- Tools are plain async fns taking `ctx: RunContext[AgentDeps]`
  (`agents/deps.py`: org_id, tavily key, fastmail creds, supabase client,
  openai key). Registered via `ts.add_function(fn, name=...)`.
- History: `db_messages_to_history` converts DB rows (user/assistant only);
  `trim_history_processor` (a `ProcessHistory` capability on every agent) does
  the trimming — 4000-TOKEN budget estimated at 4 chars/token (≈16k chars
  admitted), newest kept, orphaned leads stripped.
- Memory context: `memory/reader.py::load_memory_context` — cached rendered
  block, 500-token budget, prepended to instructions. Extraction is
  fire-and-forget post-reply (`memory/extractor.py`, Haiku, structured output;
  corrections archive the old fact and flag Jordan via Telegram).

## The instrumentation choke point

ALL agent runs (chat, proactive, events, memory extraction, evals emit) go
through `utils/agent_runner.py::run_agent_instrumented`: Logfire `agent_run`
span, latency, `extract_usage` (input/output tokens), tool-call count, cost
(`utils/pricing.py::PRICING` — update when models change), 200k token budget
guardrail, error taxonomy (`classify_error` → type + low/medium/high/critical),
fire-and-forget `save_usage_event` + PostHog `agent_run_completed`.
`RunKind` enum (`analytics/types.py`) mirrors the `usage_events.run_kind` CHECK
constraint: user_message, proactive, memory_extract, eval, event, voice.

Observability details, event catalogue, dashboard ids: `docs/observability.md`.

## Idempotency & resilience (the patterns, in one place)

| Concern | Mechanism | Where |
|---|---|---|
| Duplicate inbound | unique `channel_message_id` per channel (`telegram:{chat}:{msg}`, `app-{slug}-{key}`, `app-voice-{key}`) | `db/messages.py::message_exists` |
| Railway edge replay (>20s no response) | stable idempotency key + replay converges on original run's reply | `gateway/voice.py::await_original_reply`, `app_chat.py::replay_app_response` |
| Fire-and-forget task GC | strong-ref sets + `drain_*` helpers | `main.py`, `agent_runner.py`, `emitter.py` |
| Double proactive send | tz-aware `was_sent_today` | `proactive/delivery.py` |
| Topic bleed | 30-min idle rotation (archive + fresh conversation) | `db/conversations.py` |
| Bad config deploy | `/health` 503 gates Railway deploy: every active DB agent must have a running bot AND a model the Anthropic API serves | `health.py::build_health_report` |
| Runaway run | 200k token budget → `TokenBudgetExceededError` | `agent_runner.py` |
| Unset secret | empty-string sentinel = feature disabled (webhook 503, workout bot skipped, fastmail watcher off) | `config.py` |

Polling liveness (gap found 2026-07-07, fixed 2026-07-08): a dying polling
task (revoked token, auth failure) evicts its bot from `app.state.bots` via
`watch_polling_liveness` (`channels/telegram.py`), so `/health` degrades
instead of reporting a silent bot as running. Shutdown cancellation does not
evict.

## Database (Supabase, hosted)

Migrations `001`–`020` (005 removed as a no-op), applied by hand in the SQL
Editor — 016/019 are schema (run before their code deploy), 015/017/018/020 are
data grants/seeds (015 applied 2026-07-25; 017/018/020 run only after deploy —
headers state the ordering). Tables: organizations, agents, conversations, messages, memory_facts /
memory_events / memory_context, obsidian_notes / obsidian_note_chunks
(pgvector, 512-dim text-embedding-3-small, RPC `search_obsidian_notes`),
proactive_schedules, proactive_messages, usage_events (cost ledger), feedback,
workout_profiles / workout_plans / workout_logs, event_triggers,
watcher_cursors. RLS: deny-all on obsidian tables (service key bypasses).
Pooling: pooler port 6543 with `?pgbouncer=true`.

## Env vars (complete; `config.py::Settings` is authoritative)

Required, no default: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`,
`ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TAVILY_API_KEY`, `FASTMAIL_USERNAME`,
`FASTMAIL_APP_PASSWORD`, `OPENAI_API_KEY`, `DEFAULT_ORG_ID`.

Defaulted/optional: `DEFAULT_AGENT_SLUG` (claw-main), `WORKOUT_TELEGRAM_BOT_TOKEN`
("" = workout bot off), `WORKOUT_AGENT_SLUG` (workout-coach), `LOG_LEVEL`,
`ENVIRONMENT` (development|production), `MESSAGE_HISTORY_LIMIT` (50),
`LOGFIRE_TOKEN`, `POSTHOG_API_KEY` (project key `phc_*`, never personal `phx_*`),
`POSTHOG_HOST`, `POSTHOG_ENABLED`, `FRONTEND_ANALYTICS_TOKEN`,
`EVAL_JUDGE_MODEL`, `EVAL_TEST_ORG_ID`, `CLAW_WEBHOOK_SECRET` ("" = webhooks
disabled), `CLAW_APP_TOKEN` ("" = app/voice endpoints disabled),
`FASTMAIL_API_TOKEN` ("" = mail watching/reading off). Railway also needs
`PORT=8000` on the web service (healthcheck).

## Evals

`claw-eval run <dataset>|--all` (`evals/run_eval.py`). Registry in
`evals/registry.py`: `memory_recall` (20 cases, RequiredFactsScorer + pinned
LLMJudge) and `obsidian_retrieval` (20 cases, TopKMembershipScorer, no LLM —
embeddings + RPC against the eval org). Task model pinned in
`evals/tasks/memory_recall.py` deliberately — evals stay green independent of
DB agent config. Baselines committed in `evals/baselines/`; regression =
score < baseline − 0.05 → exit 2 → Railway cron reports failure; PostHog
`eval_run_completed` carries the flag. Fail-fast settings guard exists because
pydantic-evals silently swallows task-fn exceptions. Costs: memory_recall
~$0.10/run, obsidian_retrieval ~$0.001. Full runbook: `docs/evals.md`.

## Flutter app (thin client)

Riverpod 3 codegen + go_router shell (Home/Agents/Insights) + Playfair/Inter
sage design system. Live gating: dart-defines `GATEWAY_URL` + `CLAW_APP_TOKEN`
→ `GatewayConfig.isLive`; without them every surface is mock (what widget tests
exercise) and the sign-in screen shows. Agent ids in
`lib/shared/models/agent.dart` ARE gateway slugs. `AgentThread`
(`lib/state/app_state.dart`) is where live/mock branches.

Live today: text chat (`ApiClient.sendMessage` → `/app/messages`, per-message
idempotency key, 120s timeout, deliberate no-streaming). Built but uncalled:
`ApiClient.sendVoice` → `/voice`. Any NEW live surface must branch on
`GatewayConfig.isLive` and keep the mock path working — widget tests run in
mock mode, and an unguarded live call hits an empty baseUrl there. Stubbed: voice capture/preview (fake waveform,
placeholder transcript), passkey/magic-link (live builds skip auth — the static
token is interim auth), digest card, insights, push (Firebase deps present,
uninitialized). Blocked on Apple Developer account: DEVELOPMENT_TEAM /
archiving, APNs key, AASA hosting for passkeys+magic-link (fallback decision:
ship magic-link-only if passkeys breaks). Xcode 26.0 pin: `device_info_plus`
12.3.0 override until Xcode ≥ 26.1.

Testing: `flutter test` (mock mode; flow test uses fixed-duration pumps —
`pumpAndSettle` hangs on the typing indicator);
`flutter test integration_test -d <udid> --dart-define=...` against a LOCAL
STUB gateway (never the real gateway locally — Telegram 409; pattern in
`integration_test/live_chat_test.dart`).

## Deploy

Dockerfile (uv sync --frozen --no-dev; tests not copied) → Railway auto-deploy
on push to main → `/health` gates cutover. CI (GitHub Actions): ruff check +
format gate + pytest on push and PR. evals-cron service: same image, cron
`0 3 * * *`, start `uv run claw-eval run --all`, env by reference
`${{ jb_homebase.VAR }}`.
