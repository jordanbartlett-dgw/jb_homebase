# Observability

How Jordan Claw is instrumented and how to read the data.

## Pillars

| Layer | Tool | Source of truth for |
|---|---|---|
| Distributed tracing | Logfire | Per-request span tree, latency, model + token roll-ups |
| Per-run accounting | Supabase `usage_events` | Auditable cost ledger, BI joins, retention |
| Product analytics | PostHog | Funnels, dashboards, regression detection |

Every agent run produces all three: a Logfire trace, a `usage_events` row, and a PostHog `agent_run_completed` event. They share the same `agent_slug`, `run_kind`, `channel`, `cost_usd`, `duration_ms`, and `tool_call_count`, so cross-referencing is straightforward.

## PostHog event catalogue

| Event | distinct_id | Props |
|---|---|---|
| `agent_run_completed` | user_id (Jordan today, else org_id) | `agent_slug, run_kind, channel, conversation_id?, schedule_name?, model, input_tokens, output_tokens, cost_usd?, duration_ms, tool_call_count, success, error_type?` |
| `proactive_sent` | user_id | `schedule_name?, task_type, channel, content_length, agent_slug?, trigger` |
| `agent_session_started` | user_id | `channel, agent_slug` (emitted on conversation insert) |
| `eval_run_completed` | `system:eval` | `dataset, total_cases, passed, score, prev_score?, regression, duration_ms` |
| `feedback_submitted` | user_id | `agent_slug, rating, has_note, prompt_source, conversation_id?` |

Event names are constants in `jordan_claw.analytics.emitter.ALLOWED_EVENTS`. Never inline an event string at a call site — use the typed emitter function.

## Frontend proxy

Browser / Flutter clients hit `POST /api/analytics/event` with `Authorization: Bearer <FRONTEND_ANALYTICS_TOKEN>`. The route validates the event against `ALLOWED_EVENTS`, enriches with the server-side `org_id`, and dispatches to the same emitter functions used in-process. There is no second emission path.

## First dashboard

Build via the PostHog MCP server (install: `npx @posthog/wizard mcp add`). Claude can call `dashboard-create` + `insight-create` directly — no UI clicking required. Definitions are kept here so the dashboard is reproducible if PostHog state is lost or if the MCP is unavailable.

Pin all insights to a single dashboard named **"Jordan Claw — Production"**.

| # | Insight | Definition |
|---|---|---|
| 1 | Daily cost per agent | `agent_run_completed`, sum(`cost_usd`), breakdown `agent_slug`, daily, last 30d |
| 2 | Runs per agent per day | `agent_run_completed`, count, breakdown `agent_slug`, daily, last 30d |
| 3 | p95 latency | `agent_run_completed`, p95(`duration_ms`), breakdown `agent_slug` × `run_kind`, last 14d |
| 4 | Proactive delivery rate | `proactive_sent`, count, breakdown `schedule_name`, last 30d |
| 5 | Avg feedback per agent | `feedback_submitted`, avg(`rating`), breakdown `agent_slug`, weekly, last 90d |
| 6 | Low-rating count | `feedback_submitted` where `rating <= 2`, count, breakdown `agent_slug`, last 30d |

Insights 5 and 6 begin populating once PR4 (`feedback`) ships — defer building them until then so the dashboard doesn't show empty tiles.

## Data starts on migration date

`usage_events` begins populating at PR2 deploy time. PostHog events begin at PR3 deploy time. Week-1 dashboard views show partial days. Cost charts before the deploy date are zero. There is no backfill from `messages.token_count` or any other historical source. Future analytics tables inherit the same convention — when a new analytics surface lands, the data starts the day it lands, no historical reconstruction.

## Operating the system

- **Add a new event**: define a typed function in `analytics/emitter.py`, append the name to `ALLOWED_EVENTS`, and (if you want it callable from the browser) handle it in `analytics_proxy._dispatch`.
- **PostHog goes down**: emits become no-ops at WARN level. The agent never fails because PostHog is unavailable. Token usage is still captured in `usage_events` and Logfire.
- **Disable PostHog locally**: unset `POSTHOG_API_KEY` or set `POSTHOG_ENABLED=false`.
- **Drain the queue**: `posthog.shutdown()` is registered in the FastAPI lifespan teardown. Pending captures are awaited via `emitter.drain_pending_emits()` before shutdown.
- **PostHog "Sessions" tab is empty by design**: we use the server-side Python SDK and don't emit `$session_id`. PostHog Sessions is a frontend-SDK concept. Use Live events / the Events explorer / the dashboard above instead.
- **Project key vs. personal key**: `POSTHOG_API_KEY` must be the *Project* API key (`phc_*`) from PostHog → Project settings. The *Personal* API key (`phx_*`) from user settings will return 401 from the capture endpoint.

## Verification log

- 2026-05-04: PR3 deployed to Railway, `POSTHOG_API_KEY` (project key) and `FRONTEND_ANALYTICS_TOKEN` set. Live `agent_run_completed` events confirmed in PostHog US. `posthog_client_initialized` log line present in Railway runtime logs with no upload errors following.
