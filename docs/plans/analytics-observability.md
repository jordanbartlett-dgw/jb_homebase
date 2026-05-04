# Jordan Claw — Analytics & Observability Plan

## Context

Jordan Claw has pivoted from "multi-tenant consultancy product" to **personal agent OS** — a workbench where Jordan builds and runs a growing roster of agents and observes whether they earn their keep. Multi-tenant concerns are deferred to a future repo.

This plan stands up the observability + analytics layer that lets Jordan:

1. **Debug** individual agent runs (Logfire — already a dep, partially wired)
2. **See trends** across agents over time (PostHog — new)
3. **Catch quality regressions** on the agents that matter most (Pydantic Evals — new)
4. **Capture personal outcome signals** (did the agent actually help)

**Hard architectural rule (from spec):** Logfire is the source of truth. PostHog is a rollup. Do **not** dual-emit metrics from the agent hot path. A separate writer reads from `usage_events` (populated from Pydantic AI usage extraction) and emits PostHog events. *Confirmed via clarification: "separate writer" = same Python process, fire-and-forget asyncio task that runs AFTER `usage_events` insert; not a separate deploy target.*

---

## Findings from Investigation

### Logfire (today)
- `src/jordan_claw/main.py:54-61`: `logfire.configure(token, service_name="jordan-claw", environment)` is called conditionally on `settings.logfire_token`. `instrument_fastapi(app)` and `instrument_httpx()` are wired.
- **Gap**: `logfire.instrument_pydantic_ai()` is NOT called. Agent runs are not auto-traced today.
- No custom `logfire.span(...)` or `logfire.info(...)` calls anywhere.
- `structlog` is the primary log path, configured in `main.py:configure_logging`.

### Three `agent.run()` call sites (no shared wrapper)
1. **`src/jordan_claw/gateway/router.py:79-109`** — `handle_message`. Already has timing (`time.monotonic`), `extract_usage(result.usage())`, model name, and a `log.info("agent_run_complete", ...)` event. Saves the assistant message via `save_message(... token_count=..., model=...)` at `:123` but **never passes `cost_usd`** even though the column exists. Available context: `org_id`, `channel`, `conversation_id`, `agent_slug`.
2. **`src/jordan_claw/proactive/executors.py:63-81`** — `_run_agent_prompt`. NO instrumentation; just `result = await agent.run(...); return result.output`. The dispatcher (`proactive/scheduler.py:53-100`) holds `task_type` (= the schedule_name: `morning_briefing`, `weekly_review`, `daily_scan`, `calendar_reminder`).
3. **`src/jordan_claw/memory/extractor.py:116-172`** — `extract_memory_background`. NO instrumentation. Uses a different agent (`anthropic:claude-haiku-4-5-20251001`) with structured output (`ExtractionResult`). Caller scope has `org_id`. This is fire-and-forget already.

### Token / cost extraction
- Reusable utility at `src/jordan_claw/utils/token_counting.py` — `extract_usage(usage: RunUsage) -> dict` returns `{input_tokens, output_tokens, total_tokens, requests}`. Pydantic AI 1.75 `RunUsage` exposes `input_tokens`, `output_tokens`, `requests`. **No post-run callback hook exists** — usage must be extracted after `await agent.run()` returns.
- No pricing table, no `calculate_cost`, no `MODEL_PRICING` exists. `messages.cost_usd` column is permanently NULL.

### Schema
- Migrations in `supabase/migrations/00X_*.sql`. Latest: `005_agent_tool_routing_prompt.sql`. Next: `006_*.sql`.
- `messages` (`001_initial_schema.sql:45-56`) already has `token_count int`, `cost_usd numeric(10,6)`, `model text`, `metadata jsonb`. `cost_usd` is unwritten today.
- `conversations` has `id, org_id, agent_id, channel, channel_thread_id, user_id, metadata, status` (CHECK in `'active','archived','error'`), timestamps.
- `organizations`, `agents` (with unique `(org_id, slug)`), `memory_*`, `obsidian_*`, `proactive_schedules`, `proactive_messages` exist.
- **No** `usage_events`, `agent_runs`, `metrics`, `feedback`, or `eval_baselines` tables.
- DB pattern: direct `await client.table(X).insert(data).execute()` chains (e.g. `db/messages.py:46`); no shared helper. Each domain has its own `db/<domain>.py` file.
- Lessons to honor: no `.maybe_single().execute()` (use `.limit(1)`); run `pg_notify('pgrst', 'reload schema')` after DDL; check existing CHECK constraints before introducing new enum-like values.

### Channel adapters
- Only Telegram exists today (`src/jordan_claw/channels/telegram.py:17-85`). Two handlers registered: `CommandStart()` and a catch-all `@dp.message()`. `IncomingMessage.channel = "telegram"` is the source of truth, bound to structlog at `gateway/router.py:40`. Future channel: Flutter — design for it but only Telegram is wired today.

### Tools
- `src/jordan_claw/tools/__init__.py:12-22` — `BASE_TOOLSET = FunctionToolset()`, ten tools registered via `BASE_TOOLSET.add_function(fn, name=...)`. Per-agent filtering at `agents/factory.py:43`. No tool-level wrapping. Once `instrument_pydantic_ai()` is enabled, **`tool_name` and basic success/error appear automatically**; `empty_result` semantics require per-tool wrappers (deferred — see non-goals).

### Pydantic AI 1.75 instrumentation (verified)
- Single explicit one-liner: `logfire.instrument_pydantic_ai()` (added in `main.py` after the existing instrument calls).
- Auto attributes: `gen_ai.input.messages`, `gen_ai.output.messages`, usage tokens, tool spans.
- `Agent.metadata` is constructor-time only and doesn't create a parent grouping span — wrapping each call in `with logfire.span("agent_run", ...)` is the correct seam.

### Pydantic Evals (verified)
- Python API: `Dataset(name=..., cases=[Case(name, inputs, expected_output)], evaluators=[...]).evaluate_sync(task_fn)` returns `EvaluationReport`.
- Built-in evaluators (`IsInstance`, `LLMJudge`), custom (subclass `Evaluator`), span-based.
- Datasets: Python objects, YAML, or JSON.

### PostHog (verified)
- Package: `posthog`. Sync client, no native async — must be wrapped in `asyncio.to_thread` inside `asyncio.create_task`.
- `distinct_id` required on every capture. Not installed today.

### Test infra
- `tests/conftest.py` has only `_auto_patch_ingest_db_functions` (autouse, mocks Obsidian ingest).
- Tests mock Supabase chains in-place (`MagicMock` + `AsyncMock`). Pydantic AI tests use `model="test"` (the built-in test model). No FastAPI app/route fixtures.

### Settings
- `src/jordan_claw/config.py:Settings` is a `pydantic_settings.BaseSettings` with `.env` autoload. Adding new env vars is a one-line change each.

---

## Item 1: Logfire Labeling Pass

**Effort: S**

### Scope
Make Pydantic AI runs auto-traced, attach a consistent attribute schema to every run, defer per-tool outcome classification to phase 2b.

### Approach
1. Add `logfire.instrument_pydantic_ai()` after `main.py:61` (inside the `if settings.logfire_token:` block).
2. Standard span attribute schema, attached via `with logfire.span("agent_run", **attrs)` in the shared agent_runner wrapper (Item 2 — single seam, no per-call-site duplication):

| Attribute | Source |
|---|---|
| `agent_slug` | caller (`claw-main`, `memory-extractor`, etc.) |
| `conversation_id` | gateway only (None for proactive/memory_extract) |
| `channel` | `telegram` \| `proactive` \| `memory_extract` (synthetic for non-user runs) |
| `user_id` | hardcoded Jordan today; `IncomingMessage.user_id` later |
| `run_kind` | `user_message` \| `proactive` \| `memory_extract` \| `eval` |
| `schedule_name` | proactive only |
| `model` | from `build_agent` return tuple |

After `agent.run()` returns, set on the parent span: `usage.input_tokens`, `usage.output_tokens`, `usage.cost_usd`, `usage.duration_ms`, `usage.tool_call_count`, `outcome.success`, `outcome.error_type` (nullable).

### Files
- **Modify:** `src/jordan_claw/main.py:61` (one-line add).
- (Wrapper itself lives in Item 2 — `src/jordan_claw/utils/agent_runner.py`.)

### Schema
None.

### Dependencies
None — ships independently. Item 2's wrapper attaches the per-run attributes; without Item 2 we still get auto-tracing but no custom attributes.

### Test additions
None (manual verification: send a Telegram message, open Logfire, confirm trace shape).

### Risks
- Low. `instrument_pydantic_ai` is a documented one-liner.
- Verification gap: trace volume scales with conversation length (every tool call is a span). No quotas configured. Acceptable at single-user volume.

---

## Item 2: `usage_events` Table + Shared Agent-Run Wrapper

**Effort: M**

### Scope
The spine of the analytics layer. New table, new pricing table, new wrapper module, three call-site refactors.

### Approach

**Migration** `supabase/migrations/006_usage_events.sql`:

```sql
create table usage_events (
    id              uuid primary key default gen_random_uuid(),
    created_at      timestamptz not null default now(),
    org_id          uuid references organizations(id),
    agent_slug      text not null,
    conversation_id uuid references conversations(id) on delete set null,
    channel         text not null,
    run_kind        text not null check (run_kind in
                        ('user_message','proactive','memory_extract','eval')),
    schedule_name   text,
    model           text,
    input_tokens    int,
    output_tokens   int,
    cost_usd        numeric(10, 6),
    duration_ms     int,
    tool_call_count int not null default 0,
    success         boolean not null,
    error_type      text,
    error_severity  text check (error_severity in
                        ('low','medium','high','critical')),
    metadata        jsonb default '{}'
);
create index idx_usage_events_agent_created  on usage_events(agent_slug, created_at desc);
create index idx_usage_events_org_created    on usage_events(org_id, created_at desc);
create index idx_usage_events_kind_created   on usage_events(run_kind, created_at desc);
create index idx_usage_events_conversation   on usage_events(conversation_id) where conversation_id is not null;
alter table usage_events enable row level security;

-- Retention: not enforced. At single-user volume (~50 events/day), the table
-- will reach 100k rows in ~5 years. When count exceeds 1M or query latency
-- on indexed reads exceeds 100ms, add a pg_cron job:
--   delete from usage_events where created_at < now() - interval '18 months';
-- Same comment applies to feedback (007) and any future analytics tables.

select pg_notify('pgrst', 'reload schema');
```

`agent_slug` is denormalized text (no FK) so synthetic slugs like `memory-extractor` (not in the `agents` table) work. FKs are nullable / no-cascade so a future retention job can drop old rows without touching `conversations`. The `channel` column accepts synthetic values (`telegram`, `proactive`, `memory_extract`, future `flutter`) — single column, no separate `source`. Document this convention in the SQL comment.

**Pricing table** at `src/jordan_claw/utils/pricing.py`:

```python
# USD per 1M tokens. Source: anthropic.com/pricing as of 2026-04-15.
PRICING: dict[str, dict[str, Decimal]] = {
    "claude-sonnet-4-5-20250929": {"input": Decimal("3.00"), "output": Decimal("15.00")},
    "claude-haiku-4-5-20251001":  {"input": Decimal("1.00"), "output": Decimal("5.00")},
    "claude-sonnet-4-20250514":   {"input": Decimal("3.00"), "output": Decimal("15.00")},
}

def compute_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    pricing = PRICING.get(model)
    if not pricing:
        return None  # caller writes NULL, log warning
    return ((Decimal(input_tokens) / 1_000_000) * pricing["input"]
          + (Decimal(output_tokens) / 1_000_000) * pricing["output"])
```

Update process: hand-edit the dict + bump the date stamp on Anthropic price changes. Unknown model → `cost_usd=NULL` + `log.warning("unknown_model_pricing", model=...)`. Source-controlled (not DB) so it ships with deploys.

**Writer** at `src/jordan_claw/db/usage_events.py` — `save_usage_event(client, **fields) -> None`. Mirrors `db/messages.py:save_message` style: build dict, drop `None`s, `await client.table("usage_events").insert(data).execute()`. Also exports `most_recent_agent(client, org_id, channel, hours=24) -> str | None` for Item 5.

**Shared wrapper** at `src/jordan_claw/utils/agent_runner.py`:

```python
async def run_agent_instrumented(
    *,
    agent: Agent,
    prompt: str,
    deps: AgentDeps | None,
    db: AsyncClient,
    org_id: str,
    agent_slug: str,
    model: str,
    run_kind: RunKind,
    channel: str,
    conversation_id: str | None = None,
    schedule_name: str | None = None,
    message_history: list | None = None,
    max_total_tokens: int = 200_000,
) -> AgentRunResult: ...
```

Returns a small typed dataclass `AgentRunResult(output, usage, latency_ms, tool_call_count, model, success, error_type)`. Internals:

1. Open `with logfire.span("agent_run", **attrs)` carrying the schema in Item 1.
2. `start = time.monotonic()`.
3. `try: result = await agent.run(prompt, deps=deps, message_history=message_history)`.
4. On exception: classify `error_type` / `error_severity` per the agent-observability skill taxonomy (`provider_overloaded` / `rate_limit` / `auth` / `timeout` / `tool_error` / `unknown`), set span attrs, build a failure `AgentRunResult`, `log.exception(...)`, fire-and-forget the failure usage_event, then re-raise.
5. On success: `usage = extract_usage(result.usage())`; count tool calls via `result.all_messages()` filtered to `ToolCallPart` instances (`from pydantic_ai.messages import ToolCallPart`); `cost = compute_cost(model, usage.input_tokens, usage.output_tokens)`.
6. **Token-budget guardrail.** If `usage["total_tokens"] > max_total_tokens`: `log.warning("agent_run_token_exceeded", total=..., budget=...)`, set `error_type="token_budget_exceeded"`, `success=False`, fire the usage_event + PostHog emit, then raise a `TokenBudgetExceeded` exception. Catches runaway loops and tool-result blowups before they hit the bill. Per-agent overrides via the `agents.settings` jsonb column are deferred to phase 2b.
7. Set span attributes for usage/cost/duration/tool_count.
8. **Fire-and-forget** the `save_usage_event(...)` call via `asyncio.create_task` (keep a strong ref via module-level `set` + `task.add_done_callback(set.discard)` per the `asyncio.create_task` docs).
9. **Fire-and-forget** the PostHog `agent_run_completed` emit (Item 3).
10. Return `AgentRunResult`.

**Run kind enum** at `src/jordan_claw/analytics/types.py` — `class RunKind(StrEnum): USER_MESSAGE = "user_message"; PROACTIVE = "proactive"; MEMORY_EXTRACT = "memory_extract"; EVAL = "eval"`. Values match the migration's CHECK constraint exactly.

**Three call-site refactors (one PR, ship together):**

1. **`gateway/router.py:79-109`** — replace inline timing/usage/log block with one call to `run_agent_instrumented(... run_kind=USER_MESSAGE, channel=msg.channel, conversation_id=conversation_id ...)`. Read `result.output, result.usage, result.model` off the returned `AgentRunResult`. Keep the existing `save_message` call at `:123`; **also pass `cost_usd=result.cost_usd`** to it. `messages.cost_usd` is belt-and-suspenders redundancy: fire-and-forget `usage_events` writes can be lost; the dict-key cost on `save_message` is trivial. `usage_events` is the analytics source of truth; `messages.cost_usd` is per-message backup.
2. **`proactive/executors.py:63-81`** — `_run_agent_prompt` accepts new kwargs `agent_slug`, `schedule_name`, calls the wrapper with `run_kind=PROACTIVE, channel="proactive"`. Each executor (`execute_morning_briefing` etc.) passes `schedule_name=config.get("task_type")` through.
3. **`memory/extractor.py:128`** — replace `result = await agent.run(prompt)` with the wrapper. `agent_slug="memory-extractor"`, `run_kind=MEMORY_EXTRACT`, `channel="memory_extract"`, `conversation_id=None`. Note: the extractor agent has structured output (`output_type=ExtractionResult`); `result.output` will be the `ExtractionResult` model, not a string — verify `AgentRunResult` is generic over output type.

### Files
- **Create:**
  - `supabase/migrations/006_usage_events.sql`
  - `src/jordan_claw/db/usage_events.py`
  - `src/jordan_claw/utils/pricing.py`
  - `src/jordan_claw/utils/agent_runner.py`
  - `src/jordan_claw/analytics/__init__.py`
  - `src/jordan_claw/analytics/types.py`
- **Modify:**
  - `src/jordan_claw/gateway/router.py:76-130`
  - `src/jordan_claw/proactive/executors.py:63-81` (and call sites at `:106, :142, :226`)
  - `src/jordan_claw/memory/extractor.py:124-129`
- **Reuse:**
  - `src/jordan_claw/utils/token_counting.py:extract_usage` — call from `agent_runner`.

### Schema
Migration 006 above.

### Dependencies
- Blocks: Item 3 (PostHog uses `AgentRunResult` shape), Item 5 (most-recent-agent helper lives here).
- Blocked by: Item 1 (wrapper sets the Logfire attributes).

### Test additions
- `tests/test_agent_runner.py` — happy path with `model="test"`, error path verifying `error_type` classification, verify `tool_call_count` extraction shape.
- `tests/test_pricing.py` — known model → expected cost, unknown model → None + log.warning.
- `tests/test_db_usage_events.py` — mock client chain, verify insert payload.

### Risks
- `result.all_messages()` shape for tool counting may differ from assumption. Mitigation: write the test first; fall back to `usage.requests - 1` if the message-stream API moved in 1.75.
- `messages.cost_usd` populated alongside `usage_events.cost_usd` — same value, two writers. Acceptable redundancy (see Decision 4).
- Memory extractor's structured output (`ExtractionResult`) may break the wrapper's typing. `AgentRunResult` should be `Generic[OutputT]`.
- `TokenBudgetExceeded` (item 8) propagates as an exception — gateway `:111-120` already has the `except Exception` block that converts to `ERROR_RESPONSE` and marks the conversation `'error'`. Verify proactive and memory_extract sites also tolerate the new exception type.

---

## Item 3: PostHog Integration

**Effort: M**

### Scope
Add the `posthog` dep, add settings, add a thin emitter module, define six events, define the first dashboard. Same-process async-detached emission per the spec rule.

### Approach

**Dep**: add `posthog>=3.5.0` to `[project].dependencies` in `pyproject.toml`.

**Settings additions** in `src/jordan_claw/config.py:Settings`:
- `posthog_api_key: str | None = None`
- `posthog_host: str = "https://us.i.posthog.com"`
- `posthog_enabled: bool = True`

**Module layout:**
- `src/jordan_claw/analytics/posthog_client.py` — `get_posthog() -> Posthog | None`, lazy single-instance, returns `None` if disabled or no key.
- `src/jordan_claw/analytics/emitter.py` — typed function per event. Each function builds the props dict and calls `_capture_async(distinct_id, event, props)`, which does:

```python
async def _capture_async(distinct_id, event, props):
    client = get_posthog()
    if client is None:
        return
    def _send():
        try:
            client.capture(distinct_id=distinct_id, event=event, properties=props)
        except Exception:
            log.warning("posthog_capture_failed", event=event)
    asyncio.create_task(asyncio.to_thread(_send), name=f"posthog-{event}")
```

PostHog never raises into the caller. `posthog.shutdown()` registered in `main.py` lifespan teardown to flush the queue.

**Event catalogue** (props are positional-by-key in PostHog):

| Event | distinct_id | Props |
|---|---|---|
| `agent_run_completed` | user_id (Jordan) | `agent_slug, run_kind, channel, conversation_id?, schedule_name?, model, input_tokens, output_tokens, cost_usd?, duration_ms, tool_call_count, success, error_type?` |
| `proactive_sent` | user_id | `schedule_name, task_type, channel, content_length, agent_slug, trigger` (emitted from `proactive/delivery.py:send_proactive_message`, not the wrapper — `daily_scan` no-conflict case produces empty content + no agent run) |
| `agent_session_started` | user_id | `channel, agent_slug` (emit when `get_or_create_conversation` returns a freshly-created row) |
| `eval_run_completed` | `system:eval` | `dataset, total_cases, passed, score, prev_score?, regression, duration_ms` |
| `feedback_submitted` | user_id | `agent_slug, rating, has_note, prompt_source, conversation_id?` |
| `tool_called` | — | **DEFERRED to phase 2b** — see non-goals |

**`distinct_id` strategy:** helper `_resolve_distinct_id(user_id: str | None, org_id: str) -> str` returns `user_id or org_id`. Today single-user → resolves to `settings.default_org_id`. System events use namespaced literals (`"system:eval"`, `"system:scheduler"`).

**Failure handling:** any PostHog error swallowed and logged at WARN. The agent NEVER fails because PostHog is down.

**Frontend proxy endpoint** (designed in PR3, before Flutter exists). Adds a thin FastAPI route at `src/jordan_claw/gateway/analytics_proxy.py` mounted in `main.py`:

```
POST /api/analytics/event
Auth:  Bearer <settings.frontend_analytics_token>
Body:  {
  "event": str,         # must match an emitter function name
  "distinct_id": str,
  "properties": dict
}
Response: 202 Accepted (fire-and-forget) | 400 (unknown event) | 401 (bad token)
```

Behavior: validate `event` against an allowlist (the emitter function names exposed via `emitter.ALLOWED_EVENTS: set[str]`), enrich `properties` with the server-side `org_id` resolved from the bearer token (today: hardcoded to `default_org_id`; later: token-keyed lookup), then call the matching emitter function. **No new emission path** — Flutter calls the same emitter functions through HTTP. Settings: `frontend_analytics_token: str | None = None` in `Settings`. ~30 minutes of work in PR3 saves a refactor when Flutter ships.

**First dashboard (created in PostHog UI, queries documented in `/home/jb/Developer/jb_homebase/docs/observability.md`):**

| # | Insight | Definition |
|---|---|---|
| 1 | Daily cost per agent | `agent_run_completed`, sum(`cost_usd`), breakdown `agent_slug`, daily, last 30d |
| 2 | Runs per agent per day | `agent_run_completed`, count, breakdown `agent_slug`, daily, last 30d |
| 3 | p95 latency | `agent_run_completed`, p95(`duration_ms`), breakdown `agent_slug` × `run_kind`, last 14d |
| 4 | Proactive delivery rate | `proactive_sent`, count, breakdown `schedule_name`, last 30d (sanity check) |
| 5 | Avg feedback per agent | `feedback_submitted`, avg(`rating`), breakdown `agent_slug`, weekly, last 90d |
| 6 | Low-rating count | `feedback_submitted` where `rating <= 2`, count, breakdown `agent_slug`, last 30d |

PostHog dashboards aren't checked into git; the queries above (and the data-start note below) are documented in `docs/observability.md` so the dashboard is reproducible if PostHog state is lost.

**Data starts on migration date.** Add a section to `docs/observability.md` titled exactly that. One paragraph: `usage_events` begins populating at PR2 deploy time. Week-1 dashboard views show partial days. Cost charts before the deploy date are zero. There is no backfill from `messages.token_count` or any other historical source. Future analytics tables inherit the same convention.

### Files
- **Modify:**
  - `pyproject.toml` (add `posthog`)
  - `src/jordan_claw/config.py` (4 new settings: 3 PostHog + `frontend_analytics_token`)
  - `src/jordan_claw/main.py` (register `posthog.shutdown()` in lifespan teardown; mount the analytics proxy router)
  - `src/jordan_claw/utils/agent_runner.py` (call `emitter.agent_run_completed` after `save_usage_event`)
  - `src/jordan_claw/proactive/delivery.py` (emit `proactive_sent`)
  - `src/jordan_claw/db/conversations.py` (emit `agent_session_started` on insert path)
- **Create:**
  - `src/jordan_claw/analytics/posthog_client.py`
  - `src/jordan_claw/analytics/emitter.py` (with `ALLOWED_EVENTS: set[str]`)
  - `src/jordan_claw/gateway/analytics_proxy.py` (FastAPI router for `/api/analytics/event`)
  - `docs/observability.md` (dashboard queries + data-start note)

### Schema
None.

### Dependencies
- Blocked by: Item 2 (`AgentRunResult` shape, wrapper).
- Blocks: Item 4 dashboards (`eval_run_completed`), Item 5 dashboards (`feedback_submitted`).

### Test additions
- `tests/test_emitter.py` — mock `Posthog`, verify event/props/distinct_id per emitter function. Verify `_capture_async` swallows exceptions.
- `tests/test_posthog_client.py` — verify `get_posthog()` returns None when disabled or unkeyed.
- `tests/test_analytics_proxy.py` — auth required, allowlisted event passes through to emitter, unknown event → 400, missing token → 401, valid request → 202.

### Risks
- Event-name typos. Mitigation: emitter functions are the only source of event strings (constants per function, no string args at call sites).
- Fire-and-forget tasks GC'd before flush. Mitigation: module-level `_pending_tasks: set[asyncio.Task]` with `add_done_callback(discard)`.
- PostHog rate limits / outage. Already handled (swallow + warn).

---

## Item 4: Pydantic Evals Scaffolding + First Two Datasets

**Effort: L**

### Scope
Stand up the eval harness as a top-level `evals/` package; ship two hand-written datasets (memory_recall, obsidian_retrieval); CLI entry point; baselines in git; nightly Railway cron emits `eval_run_completed`.

### Approach

**Layout (top-level, NOT under `tests/` — evals are not pytest, they spend money):**

```
evals/
  __init__.py
  run_eval.py                    # Click CLI entry
  datasets/
    memory_recall.yaml
    obsidian_retrieval.yaml
  scorers/
    __init__.py
    memory_recall.py             # custom Evaluator subclasses + task_fn
    obsidian_retrieval.py
  fixtures/
    obsidian_corpus/             # ~30-50 sanitized notes
    memory_states/               # JSON synthetic memory states
  baselines/
    memory_recall.json           # checked into git
    obsidian_retrieval.json
  reports/                       # gitignored — per-run JSON
```

Add `evals` to `[tool.hatch.build.targets.wheel].packages` so the CLI works on Railway.

**Dataset 1 — `memory_recall` (~20 cases):**
- Each case: `inputs={memory_state, question}`, `expected_output={required_facts: list[str]}`.
- Task fn (`evals/scorers/memory_recall.py:make_task_fn`): monkeypatch `db.memory.get_active_facts` to return the case's synthetic state; run the real `claw-main` agent against the question.
- Scorers (returned alongside `Dataset(... evaluators=[...])`):
  - **`RequiredFactsScorer`** (custom `Evaluator` subclass) — substring match per required fact, score = matched / total.
  - **`LLMJudge`** (built-in) — model = `settings.eval_judge_model` (default `anthropic:claude-sonnet-4-5-20250929`), rubric = "Did the response correctly use the provided memory?"
- Cost: ~$0.10/run with sonnet; ~$30/mo at nightly cadence. Judgment quality matters more than the delta at single-user scale.

**Dataset 2 — `obsidian_retrieval` (~20 cases):**
- Each case: `inputs={query: str}`, `expected_output={expected_slugs: list[str]}`.
- Task fn: pure semantic search via the existing Obsidian search function; no agent, no model call inside scoring → zero LLM cost.
- Scorer: set-membership in top-3, score = `|expected ∩ returned| / |expected|`.
- Test corpus: same dev Supabase DB, dedicated `org_id = '00000000-0000-0000-0000-000000000eva'`. Cheaper than a separate Supabase project; isolated by org_id filter.
- **RLS verification gate (blocks PR5 merge):** before PR5 lands, verify RLS policies on `obsidian_notes` and `obsidian_note_chunks` actually filter by `org_id`. Add `tests/test_evals_isolation.py` that asserts a query authenticated as a non-eva org returns zero eva rows. If RLS isn't enforced as expected (service-role key bypasses RLS, so this test must use the anon key path), switch to a separate Supabase project before merging PR5.
- Seed script `evals/seed_corpus.py` reads from `evals/fixtures/obsidian_corpus/`, computes embeddings via OpenAI, idempotent on slug.

**CLI** (Click) at `evals/run_eval.py`:

```
[project.scripts]
claw-eval = "evals.run_eval:cli"
```

Commands:
- `claw-eval run <dataset>`
- `claw-eval run --all`
- `claw-eval run <dataset> --save-baseline`

Output: console table + JSON to `evals/reports/{dataset}_{timestamp}.json` + PostHog `eval_run_completed` emit.

**Scheduling:** Railway cron (separate deployment artifact, NOT the in-process proactive scheduler — eval runs are minutes-long and would block the 60s scheduler tick). Cron: nightly at 03:00 UTC.

**Baselines:** `evals/baselines/{dataset}.json` checked into git. Format `{dataset, score, ran_at, git_sha, cases_total, cases_passed}`. Regression flag = `current_score < baseline.score - 0.05`. Emit `regression: bool, prev_score: float` in `eval_run_completed`. PostHog action on `regression=true` → email/Slack alert (configured in PostHog UI, not code).

### Files
- **Create:** the entire `evals/` tree above.
- **Modify:**
  - `pyproject.toml` (add `[project.scripts]` entry; add `pydantic-evals` dep — verify the package name in 1.75; may be bundled with `pydantic-ai`).
  - `src/jordan_claw/config.py` (`eval_judge_model`, `eval_test_org_id`).
- **Reuse:**
  - `src/jordan_claw/analytics/emitter.py:eval_run_completed`
  - `src/jordan_claw/utils/agent_runner.py` (eval task_fns can call the wrapper with `run_kind=EVAL`).

### Schema
None — baselines are git, reports are filesystem.

### Dependencies
- Blocked by: Item 3 (emits `eval_run_completed`).
- Independent of Items 1, 2, 5 for dataset/scorer authoring (can start writing cases in parallel with Item 2).

### Test additions
- `tests/test_evals_smoke.py` — run a 2-case mini dataset against `model="test"` (asserts harness wiring, not quality).

### Risks
- Pydantic Evals API stability in 1.75 — confirmed docs exist but `pydantic-evals` may be a separate package or bundled. Verify on `pyproject.toml` add.
- Obsidian corpus embedding cost — ~50 notes × 1 embedding = ~$0.001 per seed run. Negligible.
- LLM-judge rubric drift — mitigated by checked-in baselines + the 5pp regression tolerance.
- Eval runs spending money in CI — mitigated by NOT running in CI; Railway cron only.

---

## Item 5: Outcome Instrumentation (Personal Feedback Loop)

**Effort: M**

### Scope
`feedback` table; `/feedback` Telegram command; weekly review proactive task; PostHog rating panel.

### Approach

**Migration** `supabase/migrations/007_feedback.sql`:

```sql
create table feedback (
    id              uuid primary key default gen_random_uuid(),
    created_at      timestamptz not null default now(),
    org_id          uuid references organizations(id),
    agent_slug      text not null,
    conversation_id uuid references conversations(id) on delete set null,
    rating          int not null check (rating between 1 and 5),
    note            text,
    prompt_source   text not null check (prompt_source in ('manual','weekly_review')),
    metadata        jsonb default '{}'
);
create index idx_feedback_agent_created on feedback(agent_slug, created_at desc);
create index idx_feedback_org_created   on feedback(org_id, created_at desc);
alter table feedback enable row level security;

-- Retention: not enforced (see usage_events 006 for the policy + trigger condition).
-- Apply the same pg_cron pattern when row count or query latency thresholds trip.

select pg_notify('pgrst', 'reload schema');
```

Writer at `src/jordan_claw/db/feedback.py:save_feedback(...)`.

**Telegram `/feedback` command** in `src/jordan_claw/channels/telegram.py:create_telegram_dispatcher`. Register a `Command("feedback")` handler **before** the catch-all `@dp.message()` (aiogram routes by registration order). The first positional arg can be the literal `weekly` to mark `prompt_source='weekly_review'` — explicit signaling instead of a time-window heuristic. Handler:

```python
@dp.message(Command("feedback"))
async def handle_feedback(message: types.Message) -> None:
    parts = (message.text or "").split(maxsplit=3)
    # Strip the command itself: parts[0] = "/feedback"
    rest = parts[1:]
    prompt_source = "manual"
    if rest and rest[0].lower() == "weekly":
        prompt_source = "weekly_review"
        rest = rest[1:]
    if not rest or not rest[0].isdigit() or not 1 <= int(rest[0]) <= 5:
        await message.answer("Usage: /feedback [weekly] <1-5> [note]")
        return
    rating = int(rest[0])
    note = rest[1] if len(rest) > 1 else None
    agent_slug = (await most_recent_agent(db, default_org_id, channel="telegram")
                  or default_agent_slug)
    conv_id = await most_recent_conversation_id(db, default_org_id, channel="telegram")
    await save_feedback(db, org_id=default_org_id, agent_slug=agent_slug,
                        conversation_id=conv_id, rating=rating, note=note,
                        prompt_source=prompt_source)
    await emitter.feedback_submitted(distinct_id=default_org_id,
                                     agent_slug=agent_slug, rating=rating,
                                     has_note=note is not None,
                                     prompt_source=prompt_source,
                                     conversation_id=conv_id)
    await message.answer(f"Got it. Rated {rating}/5.")
```

Helpers (in `db/usage_events.py` and `db/feedback.py`):
- `most_recent_agent(client, org_id, channel)` → query `usage_events` WHERE `org_id` AND `channel` AND `run_kind='user_message'`, ORDER BY `created_at` DESC, LIMIT 1, return `agent_slug` or None. **No time cutoff** — returns the agent the user most recently messaged on this channel, regardless of how long ago. Fallback to `default_agent_slug` happens at the call site.
- `most_recent_conversation_id(client, org_id, channel)` → query `conversations` WHERE `org_id` AND `channel` ORDER BY `updated_at` DESC LIMIT 1, return id or None.

(No `detect_feedback_source` heuristic — the explicit `weekly` arg replaces it. Less code, no time-window guessing, source attribution correct by construction.)

**Weekly review** — new task type `weekly_feedback_request`:
- Add to `EXECUTOR_MAP` in `proactive/scheduler.py:27`.
- New executor `execute_weekly_feedback_request(db, org_id, config, settings) -> str` returning a fixed string asking Jordan to rate his week with `/feedback weekly <1-5> [note]`. The string MUST instruct the `weekly` keyword explicitly so Jordan's reply is correctly attributed. **Prompt copy NOT written here** — implementer drafts; Jordan tunes.
- Seed schedule row in migration 007: cron `0 19 * * 0` (Sun 7pm), timezone `America/Chicago`.

**PostHog panels** (added to dashboard from Item 3):
- Insight 5: avg(`rating`) per `agent_slug`, weekly, last 90d.
- Insight 6: count of `rating <= 2` events per `agent_slug`, last 30d.

### Files
- **Create:**
  - `supabase/migrations/007_feedback.sql`
  - `src/jordan_claw/db/feedback.py`
- **Modify:**
  - `src/jordan_claw/channels/telegram.py:30-37` (add `/feedback` handler before catch-all; thread `db` and `default_org_id` through — already in scope)
  - `src/jordan_claw/proactive/scheduler.py:27` (add to `EXECUTOR_MAP`)
  - `src/jordan_claw/proactive/executors.py` (add `execute_weekly_feedback_request`)
  - `src/jordan_claw/db/usage_events.py` (export `most_recent_agent`)

### Schema
Migration 007 above.

### Dependencies
- Blocked by: Item 2 (`most_recent_agent` reads `usage_events`), Item 3 (`feedback_submitted` emit).
- Migration 007 lands AFTER 006.

### Test additions
- `tests/test_feedback_command.py` — happy path, invalid rating, missing args. Mock the helpers.
- `tests/test_db_feedback.py` — insert payload shape.

### Risks
- aiogram handler ordering — explicit `Command("feedback")` registered before bare `@dp.message()` wins. Verified by reading `channels/telegram.py:33-39`.
- "Most recent agent" returns whatever was most recent on this channel ever — at single-user scale this is fine; document in helper docstring.
- Forgetting the `weekly` keyword in a reply makes the rating land as `'manual'`. Mitigation: weekly_feedback_request prompt copy must be unambiguous.

---

## Cross-cutting Decisions

**Shared agent-run wrapper (`src/jordan_claw/utils/agent_runner.py`)** is the single seam. All three call sites adopt it in the same PR (Item 2's PR). No half-migrated state.

**`RunKind` StrEnum** lives at `src/jordan_claw/analytics/types.py`. The migration's CHECK constraint mirrors the enum values exactly.

**Pricing table** lives at `src/jordan_claw/utils/pricing.py`, source-controlled, manual updates with date stamp comment. Unknown model → NULL `cost_usd` + warn log.

**New env vars** (added to `Settings` in `config.py`):
- `posthog_api_key: str | None = None`
- `posthog_host: str = "https://us.i.posthog.com"`
- `posthog_enabled: bool = True`
- `frontend_analytics_token: str | None = None`
- `eval_judge_model: str = "anthropic:claude-sonnet-4-5-20250929"`
- `eval_test_org_id: str = "00000000-0000-0000-0000-000000000eva"`

---

## Recommended Sequence

```
PR 1  →  Item 1   (Logfire instrument_pydantic_ai one-liner) — SHIPS TODAY
PR 2  →  Item 2   (migration 006 + agent_runner + 3 call-site refactors + pricing)
PR 3  →  Item 3   (PostHog client, emitter, /api/analytics/event proxy, dashboard creation)
PR 4  →  Item 5   (migration 007 + /feedback command + weekly_feedback_request)
PR 5  →  Item 4   (evals scaffolding + 2 datasets + Railway cron)
```

**PR1 ships before any other work on this plan.** It is a one-line `logfire.instrument_pydantic_ai()` add inside the existing `if settings.logfire_token:` block in `main.py`. No tests, no schema, no dependencies. Shipping it first confirms Logfire is wired correctly and gives a baseline trace shape to verify against in PR2.

**Strict blocks:** PR2 ⟸ PR1 (wrapper sets the Logfire attrs); PR3 ⟸ PR2 (`AgentRunResult` shape); PR4 ⟸ PR2 + PR3; PR5 ⟸ PR3.

**Parallelizable** (can be done while PR2 is in review):
- Authoring the eval datasets/cases/fixtures (PR5 dataset content)
- PostHog UI dashboard scaffolding (no code)
- Drafting the `weekly_feedback_request` prompt copy (Item 5, separate from migration)

---

## Verification

End-to-end test path after all PRs land:

1. Send a Telegram message → confirm in Logfire: trace with `agent_run` parent span, `agent_slug=claw-main, channel=telegram, run_kind=user_message`, child `chat anthropic:*` span with `gen_ai.input.messages`.
2. Query Supabase: `select * from usage_events order by created_at desc limit 5;` → confirm row with `cost_usd` populated, `tool_call_count` matching the trace, `success=true`.
3. Open PostHog → confirm `agent_run_completed` event appeared within 30s with matching props.
4. Wait for next morning briefing (or trigger manually) → confirm `usage_events` row with `run_kind=proactive, schedule_name=morning_briefing`, PostHog `proactive_sent` event.
5. Send `/feedback 4 testing` → confirm row in `feedback` table, PostHog `feedback_submitted` event, `prompt_source='manual'`.
6. Send `/feedback weekly 5 great week` → confirm `prompt_source='weekly_review'` in the row.
7. `curl -X POST localhost:8000/api/analytics/event -H "Authorization: Bearer $FRONTEND_TOKEN" -d '{"event":"agent_run_completed","distinct_id":"test","properties":{}}'` → 202 Accepted; bad token → 401; unknown event → 400.
8. Force a token-budget exceed (set `max_total_tokens=100` for one call) → confirm `usage_events` row with `success=false, error_type='token_budget_exceeded'`, PostHog `agent_run_completed` event with same.
9. `uv run claw-eval run memory_recall` → console table shows score, `evals/reports/*.json` written, PostHog `eval_run_completed` event with `regression=false` against the seeded baseline.
10. Check the 6-insight PostHog dashboard renders without "no data" panels.

---

## Resolved Decisions

1. **Pricing table** — hand-edit `src/jordan_claw/utils/pricing.py` with a date-stamp comment on each model entry. Source-controlled, ships with deploys. No DB, no env JSON.
2. **Eval judge model** — `claude-sonnet-4-5-20250929` (default in `settings.eval_judge_model`). Judgment quality matters more than the ~$30/mo delta at single-user scale.
3. **Obsidian eval corpus location** — same dev Supabase, synthetic `org_id = '00000000-0000-0000-0000-000000000eva'`. Blocked by RLS verification gate before PR5 merges (see Item 4).
4. **`messages.cost_usd`** — keep populating it. Redundancy with `usage_events.cost_usd`; fire-and-forget `usage_events` writes can be lost; the dict-key cost on `save_message` is trivial. `usage_events` remains the analytics source of truth.
5. **`channel` enum** — synthetic values (`telegram`, `proactive`, `memory_extract`, future `flutter`). One column. Documented in the migration 006 SQL comment.
6. **Pydantic Evals package** — verify `pydantic-evals` vs. bundled-with-`pydantic-ai` on the PR5 branch before adding to `pyproject.toml`. If separate, pin to the same minor version as `pydantic-ai`.
7. **Frontend instrumentation proxy** — `/api/analytics/event` endpoint designed and shipped in PR3, before Flutter exists. ~30 minutes of work that prevents a refactor when Flutter ships. Spec in Item 3.

---

## Non-goals (explicit)

This plan does NOT cover:

- Custom in-app dashboards (PostHog is the dashboard).
- Multi-tenant cost attribution / org-level billing.
- Real-time streaming analytics (PostHog event lag is fine).
- Retention / data deletion automation (schema is friendly to a future pg_cron job; comment block in migrations 006/007 documents the trigger condition).
- Flutter / web client implementation (the `/api/analytics/event` proxy ENDPOINT ships in PR3; the Flutter caller is out of scope for this plan).
- Per-tool `empty_result` outcome classification — deferred to phase 2b after evals scaffolding lands: ~10 small PRs, one per tool. `success | error` are free from `instrument_pydantic_ai()` from day one; `empty_result` requires per-tool semantic decisions (`search_web` returning `[]` vs. `recall_memory` finding zero facts have different meanings).
- Tool re-implementation or tool-level latency wrappers beyond what `instrument_pydantic_ai()` produces.
- Prompt edits — including the `weekly_feedback_request` prompt copy (specified as requirement, not authored here).
- Agent behavior changes (no system_prompt or tool roster changes).
- Alert routing infrastructure (PostHog handles email/Slack from its UI).
- LLM-as-judge rubric tuning beyond first-pass authoring.
- Replacement of structlog (it stays as the primary log path; Logfire is for traces).
- An `eval_baselines` Supabase table (baselines stay in git for PR-reviewability).
- Backfill of historical `usage_events` from `messages` (start from migration date).
- Per-tool cost attribution (model cost is per-run, not per-tool-call).
- A `tool_called` PostHog event (deferred with phase 2b tool wrapping).
