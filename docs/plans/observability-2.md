# Observability 2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Phase 0 is fully detailed below; phases 1-4 get their own detailed plan section authored at phase start (same file, appended), grounded in the landed state of prior phases.

**Goal:** Upgrade the May-era three-pillar observability (Logfire / usage_events / PostHog) and two-dataset eval harness to current best practice: full cost coverage, PII-safe tracing, eval runs visible in Logfire Experiments, trajectory-scored evals, online evaluation of production runs, trace-attached human feedback, and alerting.

**Architecture:** Keep the existing skeleton — one choke point (`run_agent_instrumented`) feeding three sinks — and extend it: per-agent instrumentation settings via the capability registry, a `trace_id` join key on `usage_events`, eval runs promoted to first-class traced+costed workloads, and pydantic-evals 2.x online evaluation sampling production traffic. Five phases, one PR each, sequenced so each ships alone.

**Tech Stack:** pydantic-ai-slim 2.18.0, pydantic-evals 2.18.0, logfire 4.31.0, pydantic-ai-harness 0.11.0, posthog 7.x, Supabase (manual migrations), Railway.

## Decisions (locked by Jordan, 2026-07-26)

1. **PII policy:** per-agent content capture. `include_content=False` for `med-check` only (child's medical data); content stays on for `claw-main` debugging. Modest extra scrub patterns. Known limitation to document: Logfire scrubbing does NOT apply to `gen_ai.*` message attributes, so `include_content` is the only real content lever.
2. **Human feedback:** Logfire `record_feedback` (trace-attached scores, experimental API). The orphaned PostHog/Supabase feedback path gets retired in phase 4.
3. **Scope:** all 5 phases, sequential PRs.
4. **New eval datasets (phase 2):** email triage (incl. prompt-injection resistance), tool routing/trajectory, code mode.

## Global Constraints

- Python via `uv` only; `uv run pytest tests/test_x.py::test_y -v` for single tests; `uv run ruff check . && uv run ruff format --check .` before every commit.
- pydantic-ai v2 API only: `result.output`, `result.usage` (property), `input_tokens`/`output_tokens`. Load the `pydantic-ai` skill before writing agent code.
- Migrations: manual, next number **032**, header comment states deploy order, run in Supabase SQL Editor, then `SELECT pg_notify('pgrst', 'reload schema');`. **Schema expands BEFORE code that reads it merges** — Railway deploys the instant main moves.
- Agents are DB rows; granting a capability = appending its registry id to `agents.capabilities text[]` via data migration.
- Never run the gateway locally with prod tokens. Never run interactive CLI auth.
- Push to main = production deploy; verify with the `deploy-verify` skill (new SHA active + changed surface exercised).
- New tools/capabilities need wiring proofs (TestModel/FunctionModel), and the two count assertions (`tests/test_capabilities.py` N-tools test, `tests/test_tool_registry.py::EXPECTED_TOOLS`) — both skip non-ToolGroup registry entries (see `code_mode` precedent at `agents/capabilities.py:194-202`).
- Batch LLM cost discipline: test new eval datasets on 1-2 cases first, check provider billing, report projected cost before enabling nightly.
- Conventional commits; branch per phase; no em dashes in prose/docs.

---

# Phase 0 — `fix/observability-hardening`

Correctness and privacy fixes. No new features. Branch: `fix/observability-hardening`.

### Task 1: Migration 032 — usage_events.trace_id + med-check private-content grant

**Files:**
- Create: `supabase/migrations/032_observability_hardening.sql`

**Interfaces:**
- Produces: `usage_events.trace_id text` column (nullable); `med-check` agent row gains `private_content` capability id (registry entry added in Task 2 — deploy migration first, code after; unknown ids are skipped with a warning by `resolve_capabilities`, so the window is safe).

- [ ] **Step 1: Write the migration**

```sql
-- 032_observability_hardening.sql
-- Deploy order: run BEFORE merging the fix/observability-hardening branch.
-- 1) trace_id joins a usage_events row to its Logfire trace (hex trace id).
-- 2) med-check gets the private_content capability (include_content=False
--    instrumentation): its conversations carry a child's medical data and
--    must not export prompt/completion content to Logfire.

alter table usage_events add column if not exists trace_id text;

comment on column usage_events.trace_id is
  'OTel trace id (32-char hex) of the agent_run span, for Logfire cross-reference';

update agents
set capabilities = array_append(capabilities, 'private_content')
where slug = 'med-check'
  and not ('private_content' = any(capabilities));

select pg_notify('pgrst', 'reload schema');
```

- [ ] **Step 2: Apply in Supabase SQL Editor (Jordan or data-only supabase-py script), verify**

Verify with: `select trace_id from usage_events limit 1;` (column exists) and `select capabilities from agents where slug = 'med-check';` (contains `private_content`).

- [ ] **Step 3: Commit the migration file**

```bash
git add supabase/migrations/032_observability_hardening.sql
git commit -m "feat(db): usage_events.trace_id + med-check private_content grant (migration 032)"
```

### Task 2: `private_content` capability (per-agent include_content=False)

**Files:**
- Modify: `src/jordan_claw/agents/capabilities.py` (add registry entry)
- Test: `tests/test_capabilities.py` (add wiring test)

**Interfaces:**
- Consumes: `pydantic_ai.capabilities.Instrumentation`, `pydantic_ai.InstrumentationSettings`. Verify exact constructor signature in `~/.claude/skills/pydantic-ai/references/v2-capabilities.md` before writing (registry key is the DB string; it does not need to equal the capability's own id).
- Produces: registry id `"private_content"` resolvable by `resolve_capabilities`.

- [ ] **Step 1: Write the failing test**

```python
# in tests/test_capabilities.py
def test_private_content_capability_disables_content_capture():
    from pydantic_ai.capabilities import Instrumentation

    cap = CAPABILITY_REGISTRY["private_content"]
    assert isinstance(cap, Instrumentation)
    assert cap.settings.include_content is False
```

(Adjust the settings-attribute access to the real `Instrumentation` API from the skill reference; the assertion intent is fixed: content capture off.)

- [ ] **Step 2: Run it, verify it fails** (`KeyError: 'private_content'`)

- [ ] **Step 3: Implement** — in `CAPABILITY_REGISTRY`, after `code_mode`:

```python
    # Not a ToolGroup: per-agent instrumentation override. Grants NOTHING to
    # the model; it turns off prompt/completion content export to Logfire for
    # agents handling sensitive data (med-check). Logfire scrubbing does not
    # apply to gen_ai message attributes, so this is the only content lever.
    "private_content": Instrumentation(
        settings=InstrumentationSettings(include_content=False),
    ),
```

with imports `from pydantic_ai import InstrumentationSettings` and `from pydantic_ai.capabilities import Instrumentation`.

- [ ] **Step 4: Confirm the per-agent override actually wins over the global `logfire.instrument_pydantic_ai()`** — write a capture-span test (in-memory OTel exporter or logfire testing helpers, see `logfire.testing`): run a `TestModel` agent with and without the capability, assert the run span of the private agent has no `gen_ai.input.messages`/content attributes while the plain agent's does. If the override does NOT win, stop and re-plan (fallback: drop global `instrument_pydantic_ai()` and attach explicit `Instrumentation` per agent in `agents/factory.py`).

- [ ] **Step 5: Run the two count-assertion tests** — both must still pass unchanged (non-ToolGroup entries are skipped).

- [ ] **Step 6: Ruff + commit** — `feat(observability): private_content capability for med-check`

### Task 3: Scrubbing config + env hygiene

**Files:**
- Modify: `src/jordan_claw/main.py:96-104` (lifespan Logfire block)
- Modify: `.env.example` (add `LOGFIRE_TOKEN=`, `POSTHOG_API_KEY=`, `FRONTEND_ANALYTICS_TOKEN=`)
- Modify: `tests/conftest.py` (set `LOGFIRE_IGNORE_NO_CONFIG=1` before imports so no-token test runs stop emitting `LogfireNotConfiguredWarning`)

- [ ] **Step 1: Extend `logfire.configure`**

```python
        logfire.configure(
            token=settings.logfire_token,
            service_name="jordan-claw",
            environment=settings.environment,
            scrubbing=logfire.ScrubbingOptions(
                # Structured-attribute patterns only; gen_ai message content is
                # governed by include_content per agent, not scrubbing.
                extra_patterns=["date_of_birth", "dob", "app_password"],
            ),
        )
```

- [ ] **Step 2: conftest env guard**

```python
import os

os.environ.setdefault("LOGFIRE_IGNORE_NO_CONFIG", "1")
```

(top of `tests/conftest.py`, before any jordan_claw import)

- [ ] **Step 3: Run an agent-runner test file to confirm no warning noise; ruff; commit** — `fix(observability): scrubbing options + logfire env hygiene`

### Task 4: trace_id + severity + consistent span attributes in agent_runner

**Files:**
- Modify: `src/jordan_claw/utils/agent_runner.py`
- Modify: `src/jordan_claw/db/usage_events.py` (accept + insert `trace_id`)
- Modify: `src/jordan_claw/analytics/emitter.py` (`agent_run_completed` gains optional `error_severity` prop)
- Test: `tests/test_agent_runner.py`, `tests/test_db_usage_events.py`, `tests/test_emitter.py`

**Interfaces:**
- Produces: `save_usage_event(..., trace_id: str | None = None)`; every `usage_events` insert from the runner carries `trace_id`; spans on ALL exit paths carry `outcome.error_severity` when failed, and the budget path carries `usage.cost_usd` + `usage.tool_call_count`; emitter prop `error_severity: str | None`.

- [ ] **Step 1: Failing tests first**

```python
# tests/test_agent_runner.py
async def test_usage_event_carries_trace_id(...):
    # happy path against Agent("test"); after drain_pending_writes(),
    # inserted payload["trace_id"] is a 32-char lowercase hex string
    # (or None when logfire is unconfigured AND the span context is invalid;
    # assert the key is present either way)

async def test_budget_path_span_has_cost_and_tool_count(...):
    # force budget exceeded (max_total_tokens tiny); capture span attributes
    # (logfire.testing exporter); assert usage.cost_usd, usage.tool_call_count,
    # outcome.error_severity == "high" are set

async def test_error_path_span_has_severity(...):
    # FunctionModel raising TimeoutError; assert outcome.error_severity == "medium"
```

```python
# tests/test_emitter.py — extend the agent_run_completed prop assertions with
# error_severity, and the ALLOWED_EVENTS/props round-trip.
```

- [ ] **Step 2: Implement in `run_agent_instrumented`**

Right after the span opens:

```python
    with logfire.span("agent_run", **span_attrs) as span:
        ctx = span.get_span_context()
        trace_id = f"{ctx.trace_id:032x}" if ctx and ctx.trace_id else None
```

(Verify the exact accessor on `LogfireSpan` — `get_span_context()` vs `.context` — against installed logfire 4.31.0 before coding.)

Then: pass `trace_id=trace_id` to all three `save_usage_event` calls; add `error_severity` to all three `emitter.agent_run_completed` calls (`None` on success); on the exception path add `span.set_attribute("outcome.error_severity", error_severity)` and `span.record_exception(exc)`; on the budget path add the three missing attributes (`usage.cost_usd`, `usage.tool_call_count`, `outcome.error_severity`).

- [ ] **Step 3: `save_usage_event`** — add keyword-only `trace_id: str | None = None`, include in the payload via the existing drop-None logic.

- [ ] **Step 4: Run the three test files; ruff; commit** — `fix(observability): trace_id join key + consistent span attrs + severity everywhere`

### Task 5: drain usage_events writes on shutdown

**Files:**
- Modify: `src/jordan_claw/main.py:141-149` (lifespan teardown)

- [ ] **Step 1: Implement** — in the teardown block, before `await emitter.drain_pending_emits()`:

```python
    await drain_pending_writes()
```

with `from jordan_claw.utils.agent_runner import drain_pending_writes` at the top. (The docstring at `agent_runner.py:72-74` already claims this happens; this makes it true.)

- [ ] **Step 2: Check `tests/` for an existing lifespan test; extend it if present, else rely on review** (a full TestClient lifespan fixture is not worth building for one await). Ruff; commit — `fix(observability): drain pending usage_events writes on shutdown`

### Task 6: Analytics proxy — run_kind coercion, 400s, compare_digest

**Files:**
- Modify: `src/jordan_claw/gateway/analytics_proxy.py`
- Test: `tests/test_analytics_proxy.py`

**Interfaces:**
- Produces: proxy `agent_run_completed` dispatch coerces `props["run_kind"]` via `RunKind(...)`; any missing/invalid property returns HTTP 400 (not 500); bearer comparison is timing-safe.

- [ ] **Step 1: Failing tests**

```python
def test_agent_run_completed_via_proxy_dispatches(...):
    # valid body with run_kind="user_message" -> 202 and patched emitter called
    # (this currently crashes with AttributeError: 'str' object has no attribute 'value')

def test_bad_run_kind_returns_400(...):
    # run_kind="not_a_kind" -> 400

def test_missing_required_prop_returns_400(...):
    # agent_run_completed without "model" -> 400, detail "missing_property: model"
```

- [ ] **Step 2: Implement**

- `_make_auth_dep`: `if not secrets.compare_digest(authorization.removeprefix("Bearer ").strip(), token):` (import `secrets`).
- In `post_event`, wrap dispatch:

```python
        try:
            await _dispatch(body.event, body.distinct_id, body.properties, org_id)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing_property: {exc.args[0]}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- In `_dispatch` for `agent_run_completed`: `run_kind=RunKind(props["run_kind"])` (import `RunKind` from `jordan_claw.analytics.types`).

- [ ] **Step 3: Run test file; ruff; commit** — `fix(analytics): proxy run_kind coercion, 400 on bad body, timing-safe token compare`

### Task 7: Single failure log + pricing note

**Files:**
- Modify: `src/jordan_claw/gateway/router.py:123` (rename the duplicate `agent_run_failed` log event to `chat_error_response_sent`, keep its status field)
- Modify: `src/jordan_claw/utils/pricing.py` (re-verify all four rows against anthropic.com/pricing at implementation date; update the header date; keep the sonnet-5 intro-pricing note with its 2026-08-31 expiry)

- [ ] **Step 1: Make both edits (read `router.py` around line 123 first for exact context)**
- [ ] **Step 2: Grep `agent_run_failed` — exactly one emitter must remain (`agent_runner.py`); run `tests/test_pricing.py`; ruff; commit** — `fix(observability): dedupe agent_run_failed log; pricing header refresh`

### Task 8: Phase-0 doc touch-ups, PR, deploy verify

**Files:**
- Modify: `docs/observability.md` (fix only what phase 0 changed: distinct_id reality for `agent_run_completed`; drain wiring now true; trace_id column and its purpose; `error_severity` now on spans/PostHog)
- Modify: `.claude/skills/agent-observability/SKILL.md` (add `private_content` capability + trace_id join key to the skill's facts)

- [ ] **Step 1: Doc edits; commit** — `docs(observability): phase-0 accuracy pass`
- [ ] **Step 2: Open PR `fix/observability-hardening`, confirm migration 032 was applied BEFORE merge, merge**
- [ ] **Step 3: deploy-verify skill: new SHA live; then exercise: one real `/app/messages` round-trip, query the new `usage_events` row and confirm `trace_id` is populated and the trace exists in Logfire; confirm med-check runs export no message content (check one med-check trace in Logfire)**

---

# Phase 1 — `feat/cost-coverage` (detailed 2026-07-26 at phase start)

Every material paid call lands in `usage_events`; the rest gets spans; logs correlate with traces. Branch: `feat/cost-coverage`. Tasks numbered 9-17 (phase 0 used 1-8).

**Grounding corrections vs the original roadmap** (facts verified against installed packages at HEAD `2689267`):
- `RunUsage.input_tokens` is cache-INCLUSIVE (pydantic-ai normalizes Anthropic usage; cache_read/cache_write are folded in). Current `compute_cost` therefore bills cache reads at full base rate. Cache-aware pricing is a correctness fix. Field names: `cache_read_tokens`, `cache_write_tokens`.
- caldav 3.1.0 uses `niquests`, NOT `requests` — `opentelemetry-instrumentation-requests` would instrument nothing relevant. No new dependency: hand-written `logfire.span` wrappers in `tools/calendar.py` instead.
- Whisper's default response format has no duration. Switch to `response_format="verbose_json"` to get `duration` (seconds) for exact $/minute cost.
- Embeddings get a span with token/cost attributes, NOT usage_events rows: spend is ~$0.02/1M tokens and the 5 call sites + positional test fakes make row-writing invasive. Documented decision; revisit if embedding volume grows.
- The streaming path (`app_stream.py`) already runs through `run_agent_instrumented` — no new coverage needed there. Known limitations documented, not solved: code-mode inner tool calls count as one ToolCallPart; disconnected streams still bill (no counter yet).
- The 200k token budget now trips on cache-inclusive input_tokens (conservative; unchanged deliberately).

### Task 9: Migration 033 — cache token columns + run_kind expansion

Create `supabase/migrations/033_cost_coverage.sql`, applied by Jordan BEFORE merge:

```sql
-- 033_cost_coverage.sql
-- Deploy order: run BEFORE merging the feat/cost-coverage branch.
-- Adds prompt-cache token columns and two run kinds: 'classifier'
-- (voice routing haiku calls) and 'transcription' (Whisper).

alter table usage_events add column if not exists cache_read_tokens int;
alter table usage_events add column if not exists cache_write_tokens int;

-- NOTE: verify the auto-generated constraint name at apply time (see 013):
--   select conname from pg_constraint
--   where conrelid = 'usage_events'::regclass and contype = 'c';
ALTER TABLE usage_events DROP CONSTRAINT usage_events_run_kind_check;
ALTER TABLE usage_events ADD CONSTRAINT usage_events_run_kind_check
    CHECK (run_kind IN ('user_message','proactive','memory_extract','eval',
                        'event','voice','classifier','transcription'));

select pg_notify('pgrst', 'reload schema');
```

Extend `RunKind` (`analytics/types.py`) with `CLASSIFIER = "classifier"` and `TRANSCRIPTION = "transcription"`; update its docstring to cite migrations 006/013/033. Commit: `feat(db): cache token columns + classifier/transcription run kinds (migration 033)`.

### Task 10: Cache-aware usage extraction and pricing

Files: `utils/token_counting.py`, `utils/pricing.py`, `utils/agent_runner.py`, `db/usage_events.py`, `analytics/emitter.py`; tests `tests/test_pricing.py`, `tests/test_agent_runner.py`, `tests/test_db_usage_events.py`, `tests/test_emitter.py`. TDD.

- `extract_usage` adds `"cache_read_tokens": usage.cache_read_tokens or 0` and `"cache_write_tokens": usage.cache_write_tokens or 0`.
- `compute_cost` gains keyword-only `cache_read_tokens: int = 0, cache_write_tokens: int = 0`. Math (Decimal): uncached input = `max(input_tokens - cache_read - cache_write, 0)`; cost = uncached·in_rate + cache_write·in_rate·1.25 + cache_read·in_rate·0.10 + output·out_rate. Multipliers as module constants `CACHE_WRITE_MULTIPLIER = Decimal("1.25")`, `CACHE_READ_MULTIPLIER = Decimal("0.10")` with a comment citing Anthropic's published cache pricing.
- New in `pricing.py`: `WHISPER_PRICE_PER_MINUTE = Decimal("0.006")` + `compute_transcription_cost(duration_seconds: float) -> Decimal`; `EMBEDDING_PRICING = {"text-embedding-3-small": Decimal("0.02")}` ($/1M tokens) + `compute_embedding_cost(model: str, tokens: int) -> Decimal | None`. Implementer verifies both rates against OpenAI's published pricing at implementation time and dates the comment.
- `run_agent_instrumented`: pass cache counts into `compute_cost`; add span attrs `usage.cache_read_tokens`/`usage.cache_write_tokens` on success and budget paths; pass both to `save_usage_event` (new keyword-only params, drop-None) and as new props on `emitter.agent_run_completed`.
- `save_usage_event` gains `cache_read_tokens: int | None = None, cache_write_tokens: int | None = None`.
- Tests: cost math cases (pure cache-read discount, cache-write premium, zero-cache backward compat vs old values), extract_usage fields, runner payload carries cache counts, emitter props updated.

Commit: `feat(observability): cache-aware cost math + cache token capture end to end`.

### Task 11: Classifier runs land in usage_events

File: `gateway/classifier.py`; test `tests/test_classifier.py`. TDD.

Inside `classify()`, keep the existing `voice_classify` span and `build_classifier(catalog_str)` first-positional contract (tests assert it). After `result = await agent.run(transcript)`: extract usage, compute cost (`CLASSIFIER_MODEL`), set span attrs (`usage.input_tokens`, `usage.output_tokens`, `usage.cost_usd`, `usage.duration_ms`), derive trace_id exactly as `agent_runner` does, and fire-and-forget `save_usage_event(db, org_id=org_id, agent_slug="voice-classifier", conversation_id=None, channel="app-voice", run_kind=RunKind.CLASSIFIER, schedule_name=None, model=CLASSIFIER_MODEL, ..., success=True, trace_id=...)` reusing `agent_runner._fire_save` (import it; do not build a second pending-writes set). The existing broad `except` fallback path writes nothing (a failed classify costs ~0 and returns DEFAULT_AGENT). `TestModel` yields a real zero-token `RunUsage`, so existing patched tests keep passing; add a test asserting the insert payload (drain via `agent_runner.drain_pending_writes`).

Commit: `feat(observability): classifier haiku calls write usage_events`.

### Task 12: Whisper — duration, span, cost row, PostHog event

Files: `gateway/voice.py`, `main.py` (two call sites), `analytics/emitter.py`; tests `tests/test_voice_endpoint.py`, `tests/test_emitter.py`. TDD.

- `transcribe()` requests `data={"model": WHISPER_MODEL, "response_format": "verbose_json"}`; reads `text` and `duration` (float seconds, may be absent → None). Wrap the call in `logfire.span("voice_transcribe")`, set attrs `audio_bytes=len(audio)`, `duration_s`, `usage.cost_usd` (via `compute_transcription_cost`, None-safe when duration missing), `latency_ms` (monotonic).
- `transcribe()` gains keyword-only `db: AsyncClient | None = None, org_id: str | None = None`; when both provided and transcription succeeds, fire-and-forget a `save_usage_event` row: `agent_slug="whisper"`, `channel="app-voice"`, `run_kind=RunKind.TRANSCRIPTION`, `model="whisper-1"`, tokens 0/0, `cost_usd`, `duration_ms=latency_ms`, `success=True`, `trace_id` from the span. `transcribe_once` passes the kwargs through (cache hits make no provider call and write no row — the provider boundary is `transcribe`).
- New emitter `transcription_completed` (props: `duration_s: float | None`, `audio_bytes: int`, `cost_usd: float | None`, `latency_ms: int`) + ALLOWED_EVENTS + the set-equality test. Fired from `transcribe` success alongside the row (org distinct id).
- `main.py` `/voice` and `/voice/transcribe` pass `db=request.app.state.db, org_id=settings.default_org_id`. Route tests patch `transcribe` on the `main` namespace and are unaffected; the fake-httpx unit tests must update `.json()` fixtures to include `duration` and the emitter/save calls must be patched or drained there.

Commit: `feat(observability): whisper transcription cost + span + event`.

### Task 13: Embeddings span (no rows — documented decision)

File: `obsidian/embeddings.py`; test `tests/test_obsidian_embeddings.py`.

Wrap the `client.embeddings.create` call in `logfire.span("generate_embeddings")` with attrs `texts=len(texts)`, `model=EMBEDDING_MODEL`, and, when `response.usage` yields an int `prompt_tokens` (guard with `isinstance(..., int)` — test fakes return MagicMock), `usage.prompt_tokens` and `usage.cost_usd` via `compute_embedding_cost`. No DB row, no PostHog event, no signature change (so the positional test fakes in `test_care_tools.py`/`test_health_log_tools.py` keep working). Add one test with a fake response carrying real `usage.prompt_tokens`.

Commit: `feat(observability): embeddings span with token + cost attrs`.

### Task 14: structlog → Logfire bridge

Files: `main.py`; verify `logfire.StructlogProcessor` exists in installed logfire 4.31 before coding (fallback per its docs if renamed).

`configure_logging(environment, log_level, *, logfire_enabled: bool = False)`; when enabled, insert `logfire.StructlogProcessor()` into the processor chain (before the renderer) so every structlog event also lands in Logfire correlated to the active trace. Lifespan passes `logfire_enabled=bool(settings.logfire_token)`. Keep console/JSON rendering unchanged (the bridge is additive).

Commit: `feat(observability): bridge structlog events into logfire`.

### Task 15: Business events + pipeline/poller/scheduler spans

Files: `analytics/emitter.py`, `tools/email.py`, `events/pipeline.py`, `events/fastmail.py`, `events/agentmail.py`, `proactive/scheduler.py`; tests `tests/test_emitter.py`, `tests/test_email_tools.py`, `tests/test_event_pipeline.py`, `tests/test_fastmail_watcher.py`, `tests/test_agentmail_watcher.py`, `tests/test_proactive_scheduler.py`. TDD.

- New typed emitters (+ ALLOWED_EVENTS + set-equality test): `email_sent` (props: `direction: "send"|"reply"`, `message_id`, `thread_id`, `body_length: int`, `subject_length: int | None` — send only; no address/subject content, PII-light) fired in `send_email`/`reply_to_email` success paths (org distinct id from `ctx.deps.org_id`); `event_trigger_fired` (props: `trigger_name`, `source`, `outcome: "fired"|"nothing_to_send"`, `cost_usd: float | None`, `input_tokens`, `output_tokens`, `duration_ms`) fired in `_run_trigger` on both outcome branches using the in-scope `AgentRunResult`. The pipeline tests patch `run_agent_instrumented` with a `_run_result` stub — extend that helper with numeric `cost_usd`/`input_tokens`/`output_tokens`/`duration_ms` fields.
- Spans: `logfire.span("fastmail.poll")` / `logfire.span("agentmail.poll")` around each poll body with a `processed` attr set before exit; `logfire.span("event.process", source=source)` in `process_event` with `triggers`/`started` attrs; `logfire.span("proactive.dispatch", task_type=..., schedule_id=...)` wrapping `dispatch_task`'s body.
- Scheduler GC hazard: `scheduler_loop`'s `asyncio.create_task(dispatch_task(...))` holds no strong reference. Add a module-level `_pending_dispatch_tasks: set[asyncio.Task]` with add/discard (same pattern as `agent_runner._pending_writes`). No drain wiring (the loop is cancelled at shutdown).

Commit: `feat(observability): business events for email/triggers + poller and scheduler spans`.

### Task 16: CalDAV spans (no new dependency)

File: `tools/calendar.py`; test: extend the existing calendar test file.

Wrap the `asyncio.to_thread` pairs in `list_calendar_events` (`logfire.span("caldav.search")`) and `create_calendar_event` (`logfire.span("caldav.save_event")`), attrs: `username` NOT included (PII), `cached_url=bool(cache hit)` where visible, and result counts (`events=len(items)`). Rationale comment: caldav rides niquests, HTTP autoinstrumentation does not apply.

Commit: `feat(observability): caldav spans`.

### Task 17: Docs, PR, deploy verify

- `docs/observability.md`: run_kind table gains classifier/transcription; cache token columns + cache-aware cost note (incl. "input_tokens is cache-inclusive"); whisper/classifier/embeddings coverage; new PostHog events in the catalogue; structlog bridge note. `.claude/skills/agent-observability/SKILL.md`: same facts, terse.
- Open PR `feat/cost-coverage`; confirm migration 033 applied BEFORE merge; merge; deploy-verify: real voice-free check = `/app/messages` round-trip then query newest usage_events rows for cache token columns populated; confirm a `classifier` row appears after the next real voice message (or curl `/voice/messages` with a transcript); confirm structlog lines appear in Logfire.

# Phase 2 — `feat/evals-v2` (detailed plan at phase start)

Evals become traced, explained, trajectory-scored, and baseline-safe.

- `claw-eval` configures Logfire (`send_to_logfire='if-token-present'`, `service_name="claw-eval"`) + `instrument_pydantic_ai()`; `ds.evaluate(name=f"{dataset}@{git_sha}", metadata={"git_sha": ..., "target_model": ...})` → Logfire Experiments UI with per-case trace drill-down and side-by-side comparison.
- Reports persist per-case inputs, outputs, judge reasons (they are already generated and currently discarded), and `report.failures`; nonzero failures fail the run loudly.
- Per-evaluator baselines: baseline schema v2 stores each evaluator's average; regression = any evaluator drops >5pp. Kills the unweighted-composite-mean trap; composite retained only for the PostHog trend event. One-time re-baseline of all three datasets at current HEAD (memory_recall and obsidian_retrieval baselines are 3 months stale).
- Judge config: `set_default_judge_model(settings.eval_judge_model)` in the CLI; strip the 13 hardcoded per-YAML judge model strings.
- Trajectory scoring on `med_check`: `ToolCorrectness` / `TrajectoryMatch` / `MaxToolCalls` per case (expected tool sequences derived from the existing fixtures); requires `pydantic-evals[logfire]` span capture in the task runner.
- `--repeat N` flag; baseline saves use `repeat=3` with `case_groups()` averaging to damp judge variance.
- Eval runs write `usage_events` rows (`run_kind=EVAL`) with real token cost per dataset run.
- New datasets: `email_triage` (agent_inbox_review flow, incl. prompt-injection resistance cases against the PR #25 fencing), `tool_routing` (claw-main tool selection, agentic evaluators only, zero judge cost), `code_mode` (run_code used when appropriate, results incorporated). Cost-discipline: 1-2 cases first, billing check, projected nightly cost reported before enabling in `--all`.
- CLI: `list` and `compare` commands, `--json`, `--concurrency`; docs/evals.md rewritten (med_check present, TELEGRAM_BOT_TOKEN dropped from the env list).

# Phase 3 — `feat/online-evals` (detailed plan at phase start)

Production runs get scored continuously; feedback attaches to traces.

- `OnlineEvaluation` capability (pydantic-evals `online_capability`) as registry entries wired per agent: deterministic checks (`MaxToolCalls`, output-shape) at sample_rate 1.0; an LLMJudge groundedness rubric at low rate (start 0, verify cost on a trickle, then ~0.05-0.10), `sampling_mode='correlated'`, judge = `settings.eval_judge_model`. Results emit `gen_ai.evaluation.result` events → Logfire Live Evals view becomes the "are they doing a good job" screen.
- Feedback: capture `get_traceparent(span)` in `run_agent_instrumented`, persist alongside the assistant message (metadata) and expose in `AppMessageResponse`; new `POST /app/feedback` (bearer `claw_app_token`) calls `logfire.experimental.annotations.record_feedback(traceparent, 'user_rating', ...)`. Flutter UI lands separately with the TestFlight track.
- `disable_evaluation()` in tests; graceful no-op without Logfire token.

# Phase 4 — `chore/alerts-and-docs` (detailed plan at phase start)

Close the loop: alerting, tooling, truth.

- Logfire SQL alerts: agent error rate, daily cost ceiling (from `operation.cost` metrics/usage_events), trace-silence heartbeat (catches the polling-liveness class of outage), online-eval failure rate. Channel: email (Fastmail) or Slack webhook, Jordan picks at phase start.
- PostHog action/alert on `eval_run_completed regression=true` (the hook docs/evals.md already promises).
- Logfire MCP server added to Claude Code (read-scoped token — already flagged in next-steps memory) so future sessions query traces/alerts directly.
- Retire the orphaned feedback surface: drop `feedback` table + `save_feedback` + `most_recent_agent` (superseded by phase 3 trace-attached feedback). Migration 03x.
- Retention: pg_cron delete on `usage_events` (>180d) per the migration 006 comment; `evals/reports/` keep-last-N pruning in the CLI.
- Full doc refresh: `docs/observability.md`, `docs/evals.md`, `docs/architecture.md` (runner coverage claims, med_check baseline figure), root `CLAUDE.md` (Telegram removal — code is already Telegram-free), `README.md` observability section, `.claude/skills/agent-observability/SKILL.md`.

## Cost notes (LLM cost discipline)

- Phase 2 new judge-bearing datasets: ~$0.30-0.70 added per nightly run (verify against Anthropic billing after the first 1-2-case trial before enabling in `--all`).
- Phase 3 online judge at 5-10% sampling of current traffic: est. low single-digit $/month; start at 0% and raise only after billing verification.
- Everything else in this plan is deterministic/free of LLM spend.
