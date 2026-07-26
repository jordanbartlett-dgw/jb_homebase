# Observability

How Jordan Claw is instrumented and how to read the data.

## Pillars

| Layer | Tool | Source of truth for |
|---|---|---|
| Distributed tracing | Logfire | Per-request span tree, latency, model + token roll-ups |
| Per-run accounting | Supabase `usage_events` | Auditable cost ledger, BI joins, retention |
| Product analytics | PostHog | Funnels, dashboards, regression detection |

Every agent run produces all three: a Logfire trace, a `usage_events` row, and a PostHog `agent_run_completed` event. They share the same `agent_slug`, `run_kind`, `channel`, `cost_usd`, `duration_ms`, and `tool_call_count`, so cross-referencing is straightforward. `usage_events.trace_id` (32-char hex OTel trace id of the `agent_run` span) is the join key from a usage row to its Logfire trace.

`usage_events` also carries `cache_read_tokens` and `cache_write_tokens` (migration 033), and `run_kind` gained two values: `classifier` and `transcription`. Cost is cache-aware. pydantic-ai's `usage.input_tokens` is cache-INCLUSIVE, meaning cache reads and writes are folded into it. `compute_cost` (`utils/pricing.py`) backs both out before applying the base input rate, then reprices them at Anthropic's cache multipliers: 0.10x for reads, 1.25x for writes. Spans, `usage_events` rows, and the `agent_run_completed` PostHog event all carry the two cache token counts.

## PostHog event catalogue

| Event | distinct_id | Props |
|---|---|---|
| `agent_run_completed` | user_id, else org_id | `agent_slug, run_kind, channel, conversation_id?, schedule_name?, model, input_tokens, output_tokens, cost_usd?, duration_ms, tool_call_count, success, error_type?, error_severity?` |
| `proactive_sent` | user_id | `schedule_name?, task_type, channel, content_length, agent_slug?, trigger` |
| `agent_session_started` | user_id | `channel, agent_slug` (emitted on conversation insert) |
| `eval_run_completed` | `system:eval` | `dataset, total_cases, passed, score, prev_score?, regression, duration_ms` |
| `feedback_submitted` | user_id | `agent_slug, rating, has_note, prompt_source, conversation_id?` |
| `transcription_completed` | org_id | `duration_s?, audio_bytes, cost_usd?, latency_ms` |
| `email_sent` | user_id, else org_id | `direction, message_id, thread_id, body_length, subject_length?` |
| `event_trigger_fired` | user_id, else org_id | `trigger_name, source, outcome, cost_usd?, input_tokens, output_tokens, duration_ms` |

In-process runs always pass `user_id=None` to the emitter today (`utils/agent_runner.py` does not yet populate it), so `distinct_id` currently resolves to `org_id` for every in-process `agent_run_completed` event. Same today for `email_sent` and `event_trigger_fired`: both call sites pass `user_id=None`. The user_id path exists for the frontend proxy, which does supply a real user id.

Event names are constants in `jordan_claw.analytics.emitter.ALLOWED_EVENTS` (8 events, table above). Never inline an event string at a call site. Use the typed emitter function.

## Frontend proxy

Browser / Flutter clients hit `POST /api/analytics/event` with `Authorization: Bearer <FRONTEND_ANALYTICS_TOKEN>`. The route validates the event against `ALLOWED_EVENTS`, enriches with the server-side `org_id`, and dispatches to the same emitter functions used in-process. There is no second emission path.

## Coverage: classifier, whisper, embeddings

Three call sites sit outside `run_agent_instrumented` because they are not agent runs. Each is a deliberate, documented exception:

- **Classifier** (`gateway/classifier.py::classify`, the voice-routing haiku call): own Logfire span (`voice_classify`) and its own `usage_events` row, `agent_slug=voice-classifier`, `run_kind=classifier`. No PostHog emit by design. It is a per-utterance routing decision, not a user-facing run; cost still lands in the ledger.
- **Whisper** (`gateway/voice.py::transcribe`): `voice_transcribe` Logfire span plus a `usage_events` row (`agent_slug=whisper`, `run_kind=transcription`). Cost is duration-based (`compute_transcription_cost`, $0.006/min, from Whisper's `verbose_json` response), not token-based. Emits `transcription_completed` to PostHog. Both voice endpoints (`/voice` and the draft endpoint `/voice/transcribe`) pass `db`/`org_id` and write a usage row; the provider call costs money either way, so draft-only transcription is not exempt. Only a `transcribe()` call made without `db`/`org_id` (tests, other callers) skips the row and event.
- **Embeddings** (`obsidian/embeddings.py::generate_embeddings`): `generate_embeddings` Logfire span carries token count and cost as span attributes only. No `usage_events` row, no PostHog event. Documented decision: embedding spend is roughly $0.02 per 1M tokens, immaterial next to LLM cost, and vault ingest is a bulk job, not a per-user run worth a ledger row.

## Manual spans

Some call sites get no free span coverage from FastAPI/httpx/pydantic-ai autoinstrumentation, so they carry hand-written Logfire spans instead:

- `voice_transcribe` (`gateway/voice.py::transcribe`): the Whisper HTTP call.
- `fastmail.poll` / `agentmail.poll` (`events/fastmail.py`, `events/agentmail.py`): one watcher sweep, `processed` attribute.
- `event.process` (`events/pipeline.py::process_event`): webhook/poll trigger fan-out, `triggers`/`started` attributes.
- `proactive.dispatch` (`proactive/scheduler.py::dispatch_task`): one scheduler task execution, `task_type`/`schedule_id` attributes.
- `caldav.search` / `caldav.save_event` (`tools/calendar.py`): calendar IO, `events` count (search only) and `cached_url` attributes. caldav rides niquests, so httpx/requests autoinstrumentation never sees these calls; hand spans are the only coverage.

## Logfire / structlog bridge

`main.py::configure_logging` appends `logfire.StructlogProcessor(console_log=False)` to the structlog processor chain whenever a Logfire token is configured. Every structured log line (`log.info`, `log.warning`, `log.exception`, ...) now also lands in Logfire, correlated to the active trace/span. Console/JSON rendering is unchanged; `console_log=False` keeps the bridge additive so lines don't double-print.

## Production dashboard

**Name:** Jordan Claw — Production
**Dashboard id:** `1543058`
**URL:** https://us.posthog.com/project/409412/dashboard/1543058

Built via the PostHog MCP server (install: `npx @posthog/wizard mcp add`). Definitions are kept here so the dashboard is reproducible if PostHog state is lost or the MCP is unavailable. To rebuild: call `dashboard-create` then `insight-create` with `dashboards: [<dashboard_id>]` for each row below.

| # | Insight | short_id | Definition |
|---|---|---|---|
| 1 | Daily cost per agent | `gObWujy1` | `agent_run_completed`, sum(`cost_usd`), breakdown `agent_slug`, daily, last 30d, `$`-prefixed Y axis |
| 2 | Runs per agent per day | `lSiprPuZ` | `agent_run_completed`, count, breakdown `agent_slug`, daily, last 30d |
| 3 | p95 latency by agent and run kind | `MNyUxBXZ` | `agent_run_completed`, p95(`duration_ms`), breakdown `agent_slug` × `run_kind`, daily, last 14d, `duration_ms` Y axis |
| 4 | Proactive delivery rate | `jPYFbymj` | `proactive_sent`, count, breakdown `schedule_name`, daily, last 30d |
| 5 | Avg feedback per agent | `j8ldY5Dv` | `feedback_submitted`, avg(`rating`), breakdown `agent_slug`, weekly, last 90d |
| 6 | Low-rating count (rating ≤ 2) | `Qa0lS17U` | `feedback_submitted` filtered to `rating < 3` (PostHog has no `lte` operator on numerics; integer-equivalent), count, breakdown `agent_slug`, daily, last 30d |

## Data starts on migration date

`usage_events` begins populating at PR2 deploy time. PostHog events begin at PR3 deploy time. Week-1 dashboard views show partial days. Cost charts before the deploy date are zero. There is no backfill from `messages.token_count` or any other historical source. Future analytics tables inherit the same convention — when a new analytics surface lands, the data starts the day it lands, no historical reconstruction.

## Operating the system

- **Add a new event**: define a typed function in `analytics/emitter.py`, append the name to `ALLOWED_EVENTS`, and (if you want it callable from the browser) handle it in `analytics_proxy._dispatch`.
- **PostHog goes down**: emits become no-ops at WARN level. The agent never fails because PostHog is unavailable. Token usage is still captured in `usage_events` and Logfire.
- **Disable PostHog locally**: unset `POSTHOG_API_KEY` or set `POSTHOG_ENABLED=false`.
- **Drain the queue**: FastAPI lifespan teardown awaits `drain_pending_writes()` (pending `usage_events` inserts) first, then `emitter.drain_pending_emits()` (pending PostHog captures), then `posthog.shutdown()`.
- **PostHog "Sessions" tab is empty by design**: we use the server-side Python SDK and don't emit `$session_id`. PostHog Sessions is a frontend-SDK concept. Use Live events / the Events explorer / the dashboard above instead.
- **Project key vs. personal key**: `POSTHOG_API_KEY` must be the *Project* API key (`phc_*`) from PostHog → Project settings. The *Personal* API key (`phx_*`) from user settings will return 401 from the capture endpoint.

## Content privacy

Per-agent content export to Logfire is controlled by `InstrumentationSettings(include_content=...)`, granted as a capability (`private_content` in `agents/capabilities.py`). `med-check` carries it: prompts and completions for that agent no longer export to Logfire. Logfire's `ScrubbingOptions` (configured in `main.py`, patterns for `date_of_birth`, `dob`, `app_password`) do NOT apply to gen_ai message attributes, only to structured span attributes, so `include_content` is the only lever for message-level content.

## Verification log

- 2026-05-04: PR3 deployed to Railway, `POSTHOG_API_KEY` (project key) and `FRONTEND_ANALYTICS_TOKEN` set. Live `agent_run_completed` events confirmed in PostHog US. `posthog_client_initialized` log line present in Railway runtime logs with no upload errors following.
- 2026-05-04: Dashboard 1543058 created via PostHog MCP. Insights 1-4 (`agent_run_completed` + `proactive_sent`) pinned. Tiles render correctly; the `proactive_sent` tile is empty until the next proactive run fires.
- 2026-05-04: PR4 deployed to Railway, migration 007 applied. `/feedback 4 testing` and `/feedback weekly 5 great week` both produce rows in `feedback` (`prompt_source` correctly attributed) and `feedback_submitted` PostHog events with all 5 props. Cross-reference confirmed: `feedback.agent_slug` matches `most_recent_agent` from `usage_events` for the same channel. Insights 5 and 6 added to the dashboard.
- 2026-05-04: PR5 evals scaffold + 2 datasets shipped. Initial baselines: `obsidian_retrieval` 1.000 (20/20), `memory_recall` 0.975 (20/20). RLS verification gate (`tests/test_evals_isolation.py`) green — anon-key returns zero rows from `obsidian_notes` and `obsidian_note_chunks`. `eval_run_completed` event verified in PostHog. Railway cron not yet provisioned (next step).
- 2026-05-22: PR5 merged to main (commit `0f66501`). Railway cron service `evals-cron` provisioned in `JB-HomeBase/production` (id `46b6e9d6-78f2-4b22-afe1-b6e669d1e183`), schedule `0 3 * * *` UTC, start command `uv run claw-eval run --all`. First green nightly-equivalent run 18:06 UTC: `memory_recall` 0.9625 (20/20, no regression vs baseline), `obsidian_retrieval` 1.000 (20/20). Both `eval_run_completed` events visible in PostHog. Bug discovered + fixed mid-day: cron was missing `OPENAI_API_KEY`/`TAVILY_API_KEY`/`TELEGRAM_BOT_TOKEN` references; `get_settings()` raised inside each task and pydantic-evals silently dropped cases. Fix at `evals/run_eval.py` (commit `20d622f`) now validates settings at startup.

## Evals

Quality-regression layer on top of analytics. See `docs/evals.md` for the full surface — dataset catalogue, CLI usage, isolation model, Railway cron config.
