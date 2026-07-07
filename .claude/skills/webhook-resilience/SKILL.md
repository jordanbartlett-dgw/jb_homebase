---
name: webhook-resilience
description: Use when building or debugging anything async or failure-prone in jb_homebase — webhook endpoints, idempotency, duplicate or lost messages, background tasks, timeouts, retries, replay handling, graceful shutdown, or "the request ran twice" symptoms.
---

# Resilience patterns actually used in this repo

This codebase's resilience toolkit is deliberately small: idempotency keys +
dedup lookups, replay convergence, fire-and-forget tasks with strong refs, and
empty-string feature gates. There is NO task queue, NO `processed_messages` or
claim table, NO circuit breaker, NO generic retry decorator, NO FastAPI
`BackgroundTasks` — don't introduce them for a new endpoint without Jordan
signing off on the complexity.

## Idempotency (the core pattern)

Layer 1 — stable key: every inbound gets a `channel_message_id` unique per
channel, stable across retries (`telegram:{chat}:{msg}`, `app-{slug}-{key}`,
`app-voice-{key}`). Client supplies the key for HTTP channels; fallback is a
content hash (`gateway/voice.py::idempotency_key`). NEVER a server-side
per-request UUID — that's how Railway edge replays (~20s no-response → resend)
become double executions.

Layer 2 — dedup lookup before work: `db/messages.py::message_exists` /
`get_message_by_channel_id` with `.limit(1)` (never `maybe_single`).

Layer 3 — replay convergence, not rejection: a replayed slow request (agent
runs take 30–60s) skips the run and polls for the ORIGINAL run's reply —
`gateway/voice.py::await_original_reply` (2s interval, 90s cap, then 504 so
the client can retry-poll again). Both `/voice` and `/app/messages` do this.
A replay returning the same answer as the original is the success case.

## Background work

- Fire-and-forget = `asyncio.create_task` + **strong-reference set** +
  `add_done_callback(discard)`, or the task can be garbage-collected mid-run.
  Existing sets: `_pending_event_tasks` (main.py), `_pending_writes`
  (agent_runner.py), `_pending_tasks` (emitter.py).
- Every set has a `drain_*()` helper — call it in tests before asserting on
  side effects, and it runs at shutdown.
- Shutdown is the **lifespan** context manager in `main.py` (cancel polling +
  scheduler tasks, drain, close clients). Never `@app.on_event` (deprecated).

## Webhook endpoint rules (`POST /webhooks/{source}` is the template)

- Auth: shared secret via `secrets.compare_digest`; unconfigured secret =
  503 disabled, never open.
- Return 202 immediately; process in a tracked fire-and-forget task.
- Per-item isolation: `events/pipeline.py` try/excepts each trigger so one
  failure doesn't block the rest. Same in the proactive scheduler.
- Outbound dedup for scheduled sends: `was_sent_today` (tz-aware).

## Graceful degradation (fail toward the user, silently)

- Memory context load fails → empty string, run continues (`router.py`).
- Classifier fails/low confidence → `claw-main`, never an error.
- Agent run fails → conversation marked `error`, user gets the safe
  ERROR_RESPONSE; the exception lives in usage_events/Logfire, not the chat.
- Analytics down → WARN no-op.
- Poll cursors (fastmail): first poll seeds the cursor without firing (no
  backfill storm); overflow deferred to next poll.

## When something ran twice / got lost

1. Was the key stable across the retry? (Check the stored
   `channel_message_id` values for near-duplicates.)
2. Did the replay path 504? That means the original run exceeded 90s — the
   client should re-send with the SAME key and converge.
3. Lost fire-and-forget work usually means a missing strong ref or an
   exception swallowed in the task — check Logfire for the span, and known
   gap: Telegram polling-task deaths are silent (health blind spot).
