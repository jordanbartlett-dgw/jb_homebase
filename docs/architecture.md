# Architecture — Jordan Claw / jb_homebase

Maintained system map. Update this file when flows or modules change; it is the
first thing a session reads (per CLAUDE.md). Line numbers drift — treat them as
"look here first" pointers, and trust names over numbers.

Verified 2026-07-25.

## One process, three inbound surfaces, one core

Everything runs in a single FastAPI process (`main.py` lifespan): HTTP routes,
the proactive scheduler loop, and the Fastmail watcher dispatched by that
scheduler. There is no worker service, queue, or outbound channel process.

Every inbound message, regardless of channel, funnels into
`gateway/router.py::handle_message` — the single agent-run lifecycle.

### Message flow (app + voice)

- `POST /app/messages` (`main.py::app_text_message`): bearer `CLAW_APP_TOKEN`,
  explicit `agent_slug` (no classifier), dedup key `app-{slug}-{idempotency_key}`,
  replay converges via `gateway/app_chat.py::replay_app_response`. Blocking reply
  `{agent_slug, reply, conversation_id}`. Channel `app`, one conversation per
  agent (`channel_thread_id` = slug).
- App history (`gateway/app_history.py`): authenticated
  `GET /app/conversations` (created-at cursor page, optional agent filter),
  `GET /app/conversations/current?agent_slug=...` (relaunch hydration),
  `GET /app/conversations/{id}` (org-scoped read-only transcript), and
  `POST /app/conversations/new` (archives the selected agent's active session;
  the next send mints a clean one). Titles are derived from the first user
  message, so history requires no title column. Expired active sessions are
  archived during hydration as well as on send to prevent old/new UI mixing.
- `GET /app/today` (`gateway/app_today.py`): authenticated, read-only Today
  payload. Reads the latest `morning_briefing` proactive message delivered
  during the current America/Chicago day and fetches a structured Fastmail
  agenda for the requested 1–30 day window (7 by default). It never triggers
  an agent run. Calendar failure degrades to `calendar_status="unavailable"`
  while preserving the digest. Briefings are persisted directly as app
  artifacts, independent of an outbound delivery channel.
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
  (`run_kind=EVENT`), persist via
  `proactive/delivery.py::publish_proactive_message`
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
after firing. Outputs are persisted as app artifacts with same-day dedup
(`was_sent_today`) — except task_type `reminder`, which dedups on a 5-min
`was_sent_within` window so sub-daily recurring reminders can fire. Morning
briefing also seeds in-process `loop.call_later` timers for 30-min-before
calendar reminder artifacts.
Schedule rows carry `source` ('system' vs 'reminder'); the reminders tools only
ever list/cancel `source='reminder'` rows.

## Agent construction

- Config source of truth: `agents` DB row (`db/agents.py::AgentConfig`) —
  `slug`, `system_prompt`, `model` (provider-prefixed, nullable), `capabilities
  text[]`, `is_active`. Three agents: `claw-main`, `workout-coach`, `med-check`
  (app-served only, no bot). A NULL model
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
  list_reminders, cancel_reminder), **meds** (normalize_medication,
  fetch_fda_label, get_medication_profile, save_medication_profile — on
  med-check), plus read-only cross-agent views **workout_readonly** (3 read
  tools, on claw-main) and **obsidian_readonly** (search_notes + read_note, on
  workout-coach) that reuse the same tool fns — never grant a *_readonly group
  alongside its full group (duplicate names). 24 distinct tools total. Unknown
  ids are skipped with a warning (safe deploy ordering). log_workout refuses
  same-day same-activity duplicates unless allow_duplicate=true;
  amend_last_workout updates the latest log (follow-up detail was
  double-logging sessions). Med-check details, sources, and the deployed
  prompt: `docs/med-check-agent.md`.
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
  corrections archive the old fact and persist an app artifact).

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
| Duplicate inbound | stable app keys (`app-{slug}-{key}`, `app-voice-{key}`) | `db/messages.py::message_exists` |
| Railway edge replay (>20s no response) | stable idempotency key + replay converges on original run's reply | `gateway/voice.py::await_original_reply`, `app_chat.py::replay_app_response` |
| Fire-and-forget task GC | strong-ref sets + `drain_*` helpers | `main.py`, `agent_runner.py`, `emitter.py` |
| Double proactive send | tz-aware `was_sent_today` | `proactive/delivery.py` |
| Topic bleed | 30-min idle rotation (archive + fresh conversation) | `db/conversations.py` |
| Bad config deploy | `/health` 503 gates Railway deploy when an active DB agent has no resolvable model or Anthropic confirms the model is invalid | `health.py::build_health_report` |
| Runaway run | 200k token budget → `TokenBudgetExceededError` | `agent_runner.py` |
| Unset secret | empty-string sentinel = feature disabled (webhook 503, app/voice 503, fastmail watcher off) | `config.py` |

## Database (Supabase, hosted)

Migrations `001`–`022` (005 removed as a no-op), applied by hand in the SQL
Editor — 016/019/021 are schema (run before their code deploy),
015/017/018/020/022 are data grants/seeds (015 applied 2026-07-25;
017/018/020/022 run only after deploy — headers state the ordering). Tables:
organizations, agents, conversations, messages, memory_facts /
memory_events / memory_context, obsidian_notes / obsidian_note_chunks
(pgvector, 512-dim text-embedding-3-small, RPC `search_obsidian_notes`),
proactive_schedules, proactive_messages, usage_events (cost ledger), feedback,
workout_profiles / workout_plans / workout_logs, medication_profiles,
event_triggers, watcher_cursors. RLS: deny-all on obsidian tables (service key
bypasses).
Pooling: pooler port 6543 with `?pgbouncer=true`.

## Env vars (complete; `config.py::Settings` is authoritative)

Required, no default: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_ANON_KEY`,
`ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `FASTMAIL_USERNAME`,
`FASTMAIL_APP_PASSWORD`, `OPENAI_API_KEY`, `DEFAULT_ORG_ID`.

Defaulted/optional: `DEFAULT_AGENT_SLUG` (claw-main),
`WORKOUT_AGENT_SLUG` (workout-coach), `LOG_LEVEL`,
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
LLMJudge), `obsidian_retrieval` (20 cases, TopKMembershipScorer, no LLM —
embeddings + RPC against the eval org), and `med_check` (4 cases,
PhraseAssertionScorer — required/forbidden phrases plus a global forbidden
list enforcing the asymmetry rule; fixture-backed stub tools, live model).
Task model pinned in `evals/tasks/memory_recall.py` deliberately — evals stay
green independent of DB agent config; `evals/tasks/med_check.py::MED_CHECK_PROMPT`
is a second copy of the deployed med-check prompt and must be kept in sync by
hand (`docs/med-check-agent.md` has the drift note). Baselines committed in
`evals/baselines/`; regression = score < baseline − 0.05 → exit 2 → Railway
cron reports failure; PostHog `eval_run_completed` carries the flag. Fail-fast
settings guard exists because pydantic-evals silently swallows task-fn
exceptions. Costs: memory_recall ~$0.10/run, obsidian_retrieval ~$0.001. Full
runbook: `docs/evals.md`.

## Flutter app (thin client)

Riverpod 3 codegen + go_router shell (Home/Agents/History) + Playfair/Inter
monochrome/cobalt design system. Live gating: dart-defines `GATEWAY_URL` + `CLAW_APP_TOKEN`
→ `GatewayConfig.isLive`; without them every surface is mock (what widget tests
exercise) and the sign-in screen shows. Agent ids in
`lib/shared/models/agent.dart` ARE gateway slugs. `AgentThread`
(`lib/state/app_state.dart`) hydrates live transcripts through
`ConversationRepository`; history state lives in
`lib/state/conversation_state.dart`.

Live today: text chat (`ApiClient.sendMessage` → `/app/messages`, per-message
idempotency key, 120s timeout, deliberate no-streaming), current-thread
hydration, paginated read-only History, New Chat archiving, and Today
(`ApiClient.fetchToday` → `/app/today`) with a real morning briefing and
structured seven-day calendar. `TodayRepository` maps wire payloads to domain
models; `TodayController` owns refresh/loading/error state; Home, digest
detail, and Calendar remain lean views. Built but uncalled:
`ApiClient.sendVoice` → `/voice`. Any NEW live surface must branch on
`GatewayConfig.isLive` and keep the mock path working — widget tests run in
mock mode, and an unguarded live call hits an empty baseUrl there. Stubbed:
voice capture/preview (fake waveform, placeholder transcript),
passkey/magic-link (live builds skip auth — the static token is interim auth),
push (Firebase deps present, uninitialized). Blocked on Apple Developer account: DEVELOPMENT_TEAM /
archiving, APNs key, AASA hosting for passkeys+magic-link (fallback decision:
ship magic-link-only if passkeys breaks). Xcode 26.0 pin: `device_info_plus`
12.3.0 override until Xcode ≥ 26.1.

Testing: `flutter test` (mock mode; flow test uses fixed-duration pumps —
`pumpAndSettle` hangs on the typing indicator);
`flutter test integration_test -d <udid> --dart-define=...` against a LOCAL
STUB gateway (pattern in `integration_test/live_chat_test.dart`).

## Deploy

Dockerfile (uv sync --frozen --no-dev; tests not copied) → Railway auto-deploy
on push to main → `/health` gates cutover. CI (GitHub Actions): ruff check +
format gate + pytest on push and PR. evals-cron service: same image, cron
`0 3 * * *`, start `uv run claw-eval run --all`, env by reference
`${{ jb_homebase.VAR }}`.
