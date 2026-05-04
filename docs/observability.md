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
- **Drain the queue**: `posthog.shutdown()` is registered in the FastAPI lifespan teardown. Pending captures are awaited via `emitter.drain_pending_emits()` before shutdown.
- **PostHog "Sessions" tab is empty by design**: we use the server-side Python SDK and don't emit `$session_id`. PostHog Sessions is a frontend-SDK concept. Use Live events / the Events explorer / the dashboard above instead.
- **Project key vs. personal key**: `POSTHOG_API_KEY` must be the *Project* API key (`phc_*`) from PostHog → Project settings. The *Personal* API key (`phx_*`) from user settings will return 401 from the capture endpoint.

## Verification log

- 2026-05-04: PR3 deployed to Railway, `POSTHOG_API_KEY` (project key) and `FRONTEND_ANALYTICS_TOKEN` set. Live `agent_run_completed` events confirmed in PostHog US. `posthog_client_initialized` log line present in Railway runtime logs with no upload errors following.
- 2026-05-04: Dashboard 1543058 created via PostHog MCP. Insights 1-4 (`agent_run_completed` + `proactive_sent`) pinned. Tiles render correctly; the `proactive_sent` tile is empty until the next proactive run fires.
- 2026-05-04: PR4 deployed to Railway, migration 007 applied. `/feedback 4 testing` and `/feedback weekly 5 great week` both produce rows in `feedback` (`prompt_source` correctly attributed) and `feedback_submitted` PostHog events with all 5 props. Cross-reference confirmed: `feedback.agent_slug` matches `most_recent_agent` from `usage_events` for the same channel. Insights 5 and 6 added to the dashboard.
