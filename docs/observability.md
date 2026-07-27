# Observability

How Jordan Claw is instrumented and how to read the data.

## Pillars

| Layer | Tool | Source of truth for |
|---|---|---|
| Distributed tracing | Logfire | Per-request span tree, latency, model + token roll-ups |
| Per-run accounting | Supabase `usage_events` | Auditable cost ledger, BI joins, retention |
| Product analytics | PostHog | Funnels, dashboards, regression detection |

Every agent run produces all three: a Logfire trace, a `usage_events` row, and a PostHog `agent_run_completed` event. They share the same `agent_slug`, `run_kind`, `channel`, `cost_usd`, `duration_ms`, and `tool_call_count`, so cross-referencing is straightforward. `usage_events.trace_id` (32-char hex OTel trace id of the `agent_run` span) is the join key from a usage row to its Logfire trace. Every successful run also carries its W3C traceparent (same trace, span-scoped) through to the assistant message's `metadata` and the app-channel response (`AppMessageResponse.traceparent`, the `/app/messages/stream` `complete` event). That string is what a client posts back to attach feedback to the run. See "Online evaluation" and "Feedback" below.

`usage_events` also carries `cache_read_tokens` and `cache_write_tokens` (migration 033), and `run_kind` gained two values: `classifier` and `transcription`. Cost is cache-aware. pydantic-ai's `usage.input_tokens` is cache-INCLUSIVE, meaning cache reads and writes are folded into it. `compute_cost` (`utils/pricing.py`) backs both out before applying the base input rate, then reprices them at Anthropic's cache multipliers: 0.10x for reads, 1.25x for writes. Spans, `usage_events` rows, and the `agent_run_completed` PostHog event all carry the two cache token counts.

## PostHog event catalogue

| Event | distinct_id | Props |
|---|---|---|
| `agent_run_completed` | user_id, else org_id | `agent_slug, run_kind, channel, conversation_id?, schedule_name?, model, input_tokens, output_tokens, cost_usd?, duration_ms, tool_call_count, success, error_type?, error_severity?` |
| `proactive_sent` | user_id | `schedule_name?, task_type, channel, content_length, agent_slug?, trigger` |
| `agent_session_started` | user_id | `channel, agent_slug` (emitted on conversation insert) |
| `eval_run_completed` | `system:eval` | `dataset, total_cases, passed, score, prev_score?, regression, duration_ms` |
| `transcription_completed` | org_id | `duration_s?, audio_bytes, cost_usd?, latency_ms` |
| `email_sent` | user_id, else org_id | `direction, message_id, thread_id, body_length, subject_length?` |
| `event_trigger_fired` | user_id, else org_id | `trigger_name, source, outcome, cost_usd?, input_tokens, output_tokens, duration_ms` |

In-process runs always pass `user_id=None` to the emitter today (`utils/agent_runner.py` does not yet populate it), so `distinct_id` currently resolves to `org_id` for every in-process `agent_run_completed` event. Same today for `email_sent` and `event_trigger_fired`: both call sites pass `user_id=None`. The user_id path exists for the frontend proxy, which does supply a real user id.

Event names are constants in `jordan_claw.analytics.emitter.ALLOWED_EVENTS` (7 events, table above). Never inline an event string at a call site. Use the typed emitter function.

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

## Alerts

Logfire alert queries (error rate, cost ceiling, trace-silence heartbeat, online-eval failures) and the Logfire MCP setup live in `docs/alerts.md`.

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
| 5 | Eval scores over time | `hcIUgaby` | `eval_run_completed`, avg(`score`), breakdown `dataset`, daily, last 30d. Added 2026-07-05 directly in PostHog; this doc had drifted out of sync with the live dashboard until this refresh caught it up |
| 6 | Eval regressions | `TyOn7q2h` | `eval_run_completed` filtered `regression = true` (event property, boolean `exact` match on string `"true"`), count, breakdown `dataset`, daily, last 30d. Backs the regression alert below |
| 7 | Transcription cost (daily) | `eyMFzGCr` | sum(`cost_usd`) on `transcription_completed`, daily, last 30d, `$`-prefixed Y axis. Classifier and offline-eval costs are NOT in this event, they live in Supabase `usage_events` and Logfire only (see "Coverage: classifier, whisper, embeddings" above); this tile covers Whisper transcription spend exclusively. Empty as of 2026-07-27, zero `transcription_completed` events have landed in this PostHog project yet, so the tile reads $0 across the full 30d window until the first transcription fires (same "empty until first real event" pattern as `Proactive delivery rate` at launch) |

Insights 5 (`j8ldY5Dv`, avg feedback per agent) and 6 (`Qa0lS17U`, low-rating count), both built on the now-retired `feedback_submitted` event, were unpinned from the dashboard on 2026-07-27 (`dashboard-delete-tile`, tile ids `7547983`/`7547984`). The underlying insight objects still exist in PostHog (soft-delete only removes the tile) but no longer render on this dashboard.

### Regression alert

An alert (`Eval regressions > 0`, id `019fa4a2-b83b-0000-b7e0-77a6c8e79abc`) is wired to insight 6 above via the PostHog MCP `alert-create` tool: `TrendsAlertConfig` on series 0, condition `absolute_value`, threshold bounds `{upper: 0}` (type `absolute`, fires whenever the daily regression count exceeds zero), `calculation_interval: daily`, subscribed user `me@jordanbartlett.co` (PostHog user id `524929`). No manual two-click setup was needed; the MCP's `alert-create` domain covers insight-level threshold alerts directly.

## Data starts on migration date

`usage_events` begins populating at PR2 deploy time. PostHog events begin at PR3 deploy time. Week-1 dashboard views show partial days. Cost charts before the deploy date are zero. There is no backfill from `messages.token_count` or any other historical source. Future analytics tables inherit the same convention — when a new analytics surface lands, the data starts the day it lands, no historical reconstruction.

## Operating the system

- **Add a new event**: define a typed function in `analytics/emitter.py`, append the name to `ALLOWED_EVENTS`, and (if you want it callable from the browser) handle it in `analytics_proxy._dispatch`.
- **PostHog goes down**: emits become no-ops at WARN level. The agent never fails because PostHog is unavailable. Token usage is still captured in `usage_events` and Logfire.
- **Disable PostHog locally**: unset `POSTHOG_API_KEY` or set `POSTHOG_ENABLED=false`.
- **Drain the queue**: FastAPI lifespan teardown awaits `drain_pending_writes()` (pending `usage_events` inserts) first, then `emitter.drain_pending_emits()` (pending PostHog captures), then `posthog.shutdown()`.
- **PostHog "Sessions" tab is empty by design**: we use the server-side Python SDK and don't emit `$session_id`. PostHog Sessions is a frontend-SDK concept. Use Live events / the Events explorer / the dashboard above instead.
- **Project key vs. personal key**: `POSTHOG_API_KEY` must be the *Project* API key (`phc_*`) from PostHog → Project settings. The *Personal* API key (`phx_*`) from user settings will return 401 from the capture endpoint.
- **`usage_events` retention**: migration 035 schedules a daily `pg_cron` job (`usage-events-retention`, 04:30 UTC) that deletes rows older than 180 days. If `pg_cron` is unavailable on the Supabase plan, the migration skips the schedule and the delete becomes a manual runbook line — run `delete from usage_events where created_at < now() - interval '180 days';` periodically by hand.
- **Eval report retention**: `evals/run_eval.py` prunes `evals/reports/{dataset}_*.json` to the newest `REPORTS_KEEP_PER_DATASET` (10, ~10 days of nightlies) per dataset after every write, by filename sort scoped to that dataset's own files (timestamps in the name make lexicographic order chronological within one dataset's prefix; sorting across datasets together would sort on the dataset-name prefix instead of by date).

## Content privacy

Per-agent content export to Logfire is controlled by `InstrumentationSettings(include_content=...)`, granted as a capability (`private_content` in `agents/capabilities.py`). `med-check` carries it: prompts and completions for that agent no longer export to Logfire. Logfire's `ScrubbingOptions` (configured in `main.py`, patterns for `date_of_birth`, `dob`, `app_password`) do NOT apply to gen_ai message attributes, only to structured span attributes, so `include_content` is the only lever for message-level content.

## Online evaluation

Continuous scoring of production runs, via two capability entries in
`agents/capabilities.py` (evaluators defined in `agents/online_evaluators.py`):
`online_eval` (judge-bearing, granted to `claw-main` only) and
`online_eval_deterministic` (judge-free, granted to `med-check`). Migration
034 (data-only) wires both grants. Neither is a `ToolGroup`; they grant no
tools to the model, so they're already excluded from both tool-count tests.
This is a different thing from the nightly offline eval regression guard (the
two-flip small-N damping in `docs/evals.md`); online evaluation scores live
traffic continuously, offline evals score fixed datasets nightly.

Two tiers, both wired into every run through `OnlineEvaluation.wrap_run`:

- **Always on, `sample_rate=1.0`, deterministic, free**: `MaxToolCalls(20)`
  (flags runaway tool loops) and `OutputSanity` (non-empty string, under 20k
  chars).
- **Sampled, LLM judge**: a groundedness rubric (`GROUNDEDNESS_JUDGE`),
  responsive to the request, doesn't claim untaken actions, doesn't contradict
  retrieved information. Model is `settings.eval_judge_model`. Its sample rate
  is left unset on the evaluator, so it inherits the process-wide default:
  `Settings.online_eval_sample_rate` (env `ONLINE_EVAL_SAMPLE_RATE`), wired at
  startup by `main.configure_eval_defaults`. Default is `0.0`, off.

Results emit `gen_ai.evaluation.result` OTel events parented to the
`agent_run` trace (same trace as the `usage_events` row via `trace_id`).
Without a configured Logfire token, emission is a cheap no-op. An unconfigured
process never errors, it just doesn't score anything. Offline
`Dataset.evaluate()` runs never double-fire this: `should_evaluate()` skips
when already inside an evaluation context, so nightly eval runs don't also
trigger online scoring on themselves.

Agents now run with `name=<slug>` (`agents/factory.py::create_agent`, phase 3)
instead of inferring a name from the local variable every call site shared.
Online-eval results are tagged with that name as the target, so Logfire's
**Live Evals** view groups by real agent slug (`claw-main`, `med-check`), not
one collapsed `agent` bucket.

**Enable path**: judge sampling stays at 0 until deliberately raised. Raising
`ONLINE_EVAL_SAMPLE_RATE` only samples claw-main's judge — med-check runs the
`online_eval_deterministic` capability, which has no judge evaluator wired in
at all, so the process-wide sample rate has nothing to gate for that agent.
Judge-sampling med-check would need its own capability grant plus an explicit
content-privacy decision first (its content is deliberately kept out of
Logfire; the judge has `include_input=True` and its own instrumented agent).
1. Confirm `ONLINE_EVAL_SAMPLE_RATE` is unset (or 0). Deterministic checks
   already run at 1.0 regardless, only the judge is gated.
2. Billing-check the judge model's per-call cost (LLM cost discipline: test on
   a trickle first, check actual provider billing, don't trust an internal
   estimate).
3. Set `ONLINE_EVAL_SAMPLE_RATE` on Railway on the `jb_homebase` service:
   `railway variables set -s jb_homebase ONLINE_EVAL_SAMPLE_RATE=<rate>`.
   Always pass `-s`; the CLI's sticky default service has landed vars on
   `evals-cron` before.
4. Verify in Logfire Live Evals: `groundedness` results appear alongside
   `MaxToolCalls`/`OutputSanity` for claw-main, grouped by agent slug — and
   confirm no `groundedness` results appear for med-check.

## Feedback

`POST /app/feedback` (bearer app token, same auth as the other `/app/*`
routes) attaches user feedback to a completed run's trace:

```json
{"traceparent": "00-<32hex>-<16hex>-<2hex>", "name": "helpful", "value": true, "comment": "optional, max 2000 chars"}
```

- `traceparent`: the W3C string from the assistant message / app response
  (see "Pillars" above). Identifies which trace the feedback attaches to.
- `name`: `^[a-z_]{1,32}$`.
- `value`: `bool | int | float | str` with strict member types (a `bool`
  never silently coerces to `0`/`1`). Logfire renders each differently:
  numbers as scores, strings as labels, bools as assertions.
- Handler: `gateway/app_feedback.py::record_app_feedback` calls
  `logfire.experimental.annotations.record_feedback`, attaching the score/
  label/assertion directly to the trace. Unified in Logfire's UI with the
  automated online-eval results on that same trace.
- Returns `202 {"status": "recorded"}` on success, `503` if no Logfire token
  is configured (feedback surface disabled), `502` if Logfire rejects the
  call.

Flutter UI for submitting feedback is deferred to the TestFlight track. The
endpoint exists, nothing in the app calls it yet.

The old PostHog `feedback_submitted` path (`/feedback` bot command →
`feedback` table → `most_recent_agent`) is retired (migration 035): the
`feedback` table is dropped, `save_feedback` and `most_recent_agent` are
deleted, and `feedback_submitted` is removed from `ALLOWED_EVENTS`. This
trace-attached path is the only feedback surface now.

## Verification log

- 2026-05-04: PR3 deployed to Railway, `POSTHOG_API_KEY` (project key) and `FRONTEND_ANALYTICS_TOKEN` set. Live `agent_run_completed` events confirmed in PostHog US. `posthog_client_initialized` log line present in Railway runtime logs with no upload errors following.
- 2026-05-04: Dashboard 1543058 created via PostHog MCP. Insights 1-4 (`agent_run_completed` + `proactive_sent`) pinned. Tiles render correctly; the `proactive_sent` tile is empty until the next proactive run fires.
- 2026-05-04: PR4 deployed to Railway, migration 007 applied. `/feedback 4 testing` and `/feedback weekly 5 great week` both produce rows in `feedback` (`prompt_source` correctly attributed) and `feedback_submitted` PostHog events with all 5 props. Cross-reference confirmed: `feedback.agent_slug` matches `most_recent_agent` from `usage_events` for the same channel. Insights 5 and 6 added to the dashboard.
- 2026-05-04: PR5 evals scaffold + 2 datasets shipped. Initial baselines: `obsidian_retrieval` 1.000 (20/20), `memory_recall` 0.975 (20/20). RLS verification gate (`tests/test_evals_isolation.py`) green — anon-key returns zero rows from `obsidian_notes` and `obsidian_note_chunks`. `eval_run_completed` event verified in PostHog. Railway cron not yet provisioned (next step).
- 2026-05-22: PR5 merged to main (commit `0f66501`). Railway cron service `evals-cron` provisioned in `JB-HomeBase/production` (id `46b6e9d6-78f2-4b22-afe1-b6e669d1e183`), schedule `0 3 * * *` UTC, start command `uv run claw-eval run --all`. First green nightly-equivalent run 18:06 UTC: `memory_recall` 0.9625 (20/20, no regression vs baseline), `obsidian_retrieval` 1.000 (20/20). Both `eval_run_completed` events visible in PostHog. Bug discovered + fixed mid-day: cron was missing `OPENAI_API_KEY`/`TAVILY_API_KEY`/`TELEGRAM_BOT_TOKEN` references; `get_settings()` raised inside each task and pydantic-evals silently dropped cases. Fix at `evals/run_eval.py` (commit `20d622f`) now validates settings at startup.
- 2026-07-27: Dashboard + regression alert refresh via PostHog MCP. Discovered the live dashboard already had a 7th tile (`Eval scores over time`, `hcIUgaby`, added 2026-07-05) that this doc never recorded; added it to the table. Created insight `Eval regressions` (`TyOn7q2h`, id `10493401`), pinned; created insight `Transcription cost (daily)` (`eyMFzGCr`, id `10493403`), pinned, reads $0 today, zero `transcription_completed` events exist in the project yet. Created alert `Eval regressions > 0` (id `019fa4a2-b83b-0000-b7e0-77a6c8e79abc`) on the regressions insight via `alert-create`, threshold count > 0 daily, confirmed via `alerts-list`. Unpinned the two `feedback_submitted`-based tiles (`j8ldY5Dv`, `Qa0lS17U`) via `dashboard-delete-tile`; underlying insights preserved (soft-delete). `dashboard-get` readback after all mutations confirms 7 tiles: the 4 original + `hcIUgaby` + the 2 new, feedback tiles gone.

## Evals

Quality-regression layer on top of analytics. See `docs/evals.md` for the full surface — dataset catalogue, CLI usage, isolation model, Railway cron config.
