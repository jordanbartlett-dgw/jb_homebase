---
name: agent-observability
description: Use when adding or debugging observability in jb_homebase — Logfire traces, token/cost tracking, usage_events, PostHog events, structured logging, error classification, or "why did the agent do that" questions about production behavior.
---

# Observability in the Claw

One run → three signals sharing keys (`agent_slug`, `run_kind`, `channel`,
`cost_usd`, `duration_ms`, `tool_call_count`): **Logfire** (traces), **Supabase
`usage_events`** (cost ledger — the canonical table, not `messages`), **PostHog**
(product analytics). Operational catalogue and dashboard ids: `docs/observability.md`.

## The choke point — instrument here, nowhere else

Every agent run goes through `utils/agent_runner.py::run_agent_instrumented`.
It already does: `agent_run` Logfire span, latency, usage extraction, tool-call
count, cost, 200k token budget guardrail, error classification, fire-and-forget
`save_usage_event` + PostHog emit. If you need a new per-run signal, add it
there — never in individual callers.

## pydantic-ai v2 API (the repo is v2; v1 forms are bugs)

```python
result = await agent.run(prompt, deps=deps, message_history=history)
result.output              # NOT result.data
usage = result.usage       # attribute, NOT result.usage()
usage.input_tokens         # NOT request_tokens
usage.output_tokens        # NOT response_tokens
```

Cost: `utils/pricing.py::PRICING` — USD per 1M tokens, keyed by unprefixed
model name (`compute_cost` strips `anthropic:`). Retired models stay in the
table for historical pricing. **Adding/changing a model in the DB means adding
its pricing row**, or cost silently becomes None (logged warning).

Error taxonomy: `classify_error` returns `(error_type, severity)` with severity
in `low/medium/high/critical` — this mirrors the `usage_events` CHECK
constraint. Don't invent new severities without a migration.

## PostHog rules

- Event names ONLY from `analytics/emitter.ALLOWED_EVENTS`; add new events as
  typed functions in `emitter.py`, never inline strings.
- Emits are fire-and-forget (`asyncio.to_thread`, strong-ref set); PostHog down
  = WARN no-op, an agent run must never fail on analytics.
- Project key `phc_*`, never a personal `phx_*` key.
- Frontend events go through `POST /api/analytics/event`
  (`gateway/analytics_proxy.py`, bearer `FRONTEND_ANALYTICS_TOKEN`) so the
  server enriches org_id and enforces the same allowlist.

## Logfire / logging setup

Configured once in `main.py` lifespan: `logfire.configure` + FastAPI/httpx/
pydantic-ai instrumentation, structlog with stdlib `BoundLogger`. Prod check is
`settings.environment == "production"` (there is no `railway_environment`).
Health surface is `/health` only — there is no `/metrics` endpoint; don't add
one without a reason, the three-pillar setup covers it.

## Debugging a production run

1. Logfire: find the `agent_run` span by agent_slug/time — tool calls, timings,
   and the error (if any) are on the span.
2. `usage_events`: query by `run_kind`/`agent_slug`/`created_at` for cost,
   success flag, error_type/severity. Failed runs live here with
   `success=false` (not as system-role messages).
3. PostHog `agent_run_completed` for trend context; dashboard 1543058.
4. Background writes are fire-and-forget — in tests call
   `drain_pending_writes()` / `drain_pending_emits()` before asserting.

## Anti-patterns

- Instrumenting in a caller instead of `run_agent_instrumented`.
- `result.data`, `result.usage()`, `request_tokens` — v1 fossils; the audit
  found and purged these once already.
- Inline PostHog event strings; personal API keys; blocking emits.
- Reading cost from `messages` instead of `usage_events`.
