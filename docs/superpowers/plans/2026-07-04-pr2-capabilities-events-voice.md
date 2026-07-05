# PR2: Capabilities Architecture + Event Triggers + Voice Routing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt pydantic-ai v2's capabilities architecture, add event-driven triggers (generic webhook + Fastmail watcher), and add a voice ingestion endpoint with a classifier that routes utterances to the right agent.

**Architecture:** Three phases, each independently shippable on the branch. Phase A converts the 16-tool flat registry into capability bundles (`ToolGroup(AbstractCapability)`) selected per-agent from DB config, replacing name-based tool filtering, and flips `end_strategy` to v2's `graceful` default with a semantics-documenting test. Phase B adds a `POST /webhooks/{source}` surface plus a JMAP-polling Fastmail watcher, both normalizing into an event-trigger pipeline (DB-configured triggers → agent run → Telegram delivery). Phase C adds `POST /voice`: Whisper transcription → Haiku classifier (structured output) → existing gateway path → JSON reply.

**Tech Stack:** pydantic-ai 2.5.x capabilities API, FastAPI, Supabase (migrations 012/013), httpx (JMAP + OpenAI Whisper — no new deps), aiogram delivery reuse.

**Branch:** `feature/capabilities-events-voice` off main.

**Decisions already made with Jordan:** generic webhook + Fastmail as proof source; `end_strategy='graceful'` adopted in this PR; Whisper via existing OpenAI key. Decision made in planning, flag in PR: capability bundles are coarser than per-tool filtering — workout-coach gains `forget_memory` (bundled with `recall_memory`); harmless, same-org facts.

**Secrets Jordan must add to Infisical BEFORE Phase B/C deploy:** `FASTMAIL_API_TOKEN` (JMAP API token, Fastmail Settings → Privacy & Security → API tokens, scope: mail read), `CLAW_WEBHOOK_SECRET` (any long random string), `CLAW_APP_TOKEN` (any long random string; interim voice auth until Flutter's Supabase auth lands).

**Rollout order (same pattern as PR1/migration 011):** migrations 012 + 013 apply to prod Supabase BEFORE merge (both are additive/backfill, harmless under current code). Then merge → Railway deploys.

**API-signature caution:** v2 capability API details (`AbstractCapability` field semantics, `load_capability` behavior) were verified against docs, not the installed 2.5.0, except where PR1 already probed them. Task A1 Step 1 verifies signatures; adapt call sites if they differ.

---

## Phase A: Capabilities architecture

### Task A1: ToolGroup capability + registry

**Files:**
- Create: `src/jordan_claw/agents/capabilities.py`
- Test: `tests/test_capabilities.py`

- [ ] **Step 1: Verify the v2 surface this phase relies on**

```bash
uv run python - <<'EOF'
import inspect
from pydantic_ai.capabilities import AbstractCapability
print([m for m in ('get_toolset','get_instructions','id','description','defer_loading') if hasattr(AbstractCapability, m) or m in getattr(AbstractCapability, '__dataclass_fields__', {})])
print(inspect.signature(AbstractCapability.get_toolset) if hasattr(AbstractCapability,'get_toolset') else 'no get_toolset')
EOF
```

Expected: `get_toolset`/`get_instructions` exist as overridable methods; `id`/`description`/`defer_loading` are recognized fields. If the shape differs, adapt Step 2 to the real API and note it in the commit message.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_capabilities.py
from __future__ import annotations

import pytest

from jordan_claw.agents.capabilities import CAPABILITY_REGISTRY, resolve_capabilities


def test_registry_covers_all_sixteen_tools():
    tool_names = set()
    for group in CAPABILITY_REGISTRY.values():
        tool_names.update(group.toolset.tools)
    assert len(tool_names) == 16


def test_expected_groups_exist():
    assert set(CAPABILITY_REGISTRY) == {"core", "web", "calendar", "memory", "obsidian", "workout"}


def test_resolve_capabilities_maps_ids():
    groups = resolve_capabilities(["core", "workout"])
    assert [g.id for g in groups] == ["core", "workout"]


def test_resolve_capabilities_skips_unknown_with_warning():
    groups = resolve_capabilities(["core", "nonexistent"])
    assert [g.id for g in groups] == ["core"]
```

Run: `uv run pytest tests/test_capabilities.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# src/jordan_claw/agents/capabilities.py
from __future__ import annotations

from dataclasses import dataclass

import structlog
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.tools.calendar import check_calendar, schedule_event
from jordan_claw.tools.memory import forget_memory, recall_memory
from jordan_claw.tools.obsidian import create_source_note, read_note, search_notes
from jordan_claw.tools.time import current_datetime
from jordan_claw.tools.web_search import fetch_article, search_web
from jordan_claw.tools.workout import (
    get_recent_workouts,
    get_workout_plan,
    get_workout_profile_tool,
    log_workout,
    save_workout_plan_tool,
    save_workout_profile,
)

log = structlog.get_logger()


@dataclass
class ToolGroup(AbstractCapability[AgentDeps]):
    """A named bundle of tools an agent can be granted via DB config."""

    id: str
    description: str
    toolset: FunctionToolset[AgentDeps]
    group_instructions: str | None = None
    defer_loading: bool = False

    def get_toolset(self):
        return self.toolset

    def get_instructions(self):
        return self.group_instructions


def _toolset(*fns_and_names: tuple) -> FunctionToolset[AgentDeps]:
    ts: FunctionToolset[AgentDeps] = FunctionToolset()
    for fn, name in fns_and_names:
        ts.add_function(fn, name=name)
    return ts


CAPABILITY_REGISTRY: dict[str, ToolGroup] = {
    "core": ToolGroup(
        id="core",
        description="Time and date awareness.",
        toolset=_toolset((current_datetime, "current_datetime")),
    ),
    "web": ToolGroup(
        id="web",
        description="Web search and article fetching.",
        toolset=_toolset((search_web, "search_web"), (fetch_article, "fetch_article")),
    ),
    "calendar": ToolGroup(
        id="calendar",
        description="Read and write Jordan's Fastmail calendar.",
        toolset=_toolset((check_calendar, "check_calendar"), (schedule_event, "schedule_event")),
    ),
    "memory": ToolGroup(
        id="memory",
        description="Recall and archive long-term facts about Jordan.",
        toolset=_toolset((recall_memory, "recall_memory"), (forget_memory, "forget_memory")),
    ),
    "obsidian": ToolGroup(
        id="obsidian",
        description="Search, read, and create notes in Jordan's Obsidian vault.",
        toolset=_toolset(
            (search_notes, "search_notes"),
            (read_note, "read_note"),
            (create_source_note, "create_source_note"),
        ),
    ),
    "workout": ToolGroup(
        id="workout",
        description="Training profile, plans, workout logging and history.",
        toolset=_toolset(
            (get_workout_profile_tool, "get_workout_profile"),
            (save_workout_profile, "save_workout_profile"),
            (get_workout_plan, "get_workout_plan"),
            (save_workout_plan_tool, "save_workout_plan"),
            (log_workout, "log_workout"),
            (get_recent_workouts, "get_recent_workouts"),
        ),
    ),
}


def resolve_capabilities(ids: list[str]) -> list[ToolGroup]:
    groups: list[ToolGroup] = []
    for cid in ids:
        group = CAPABILITY_REGISTRY.get(cid)
        if group is None:
            log.warning("unknown_capability_skipped", capability_id=cid)
            continue
        groups.append(group)
    return groups
```

NOTE: exact import names for tool functions must be checked against `src/jordan_claw/tools/__init__.py` lines 21-36 (e.g. `get_workout_profile_tool` vs `get_workout_profile`) — mirror what `__init__.py` imports today. `fetch_article` may live in a different module than web_search; check and fix imports accordingly. If `fetch_article`'s home module differs, keep the group assignment (web) regardless.

- [ ] **Step 4: Run tests** → 4 passed. **Step 5: Commit** `feat(agents): capability registry with six tool groups`

### Task A2: Migration 012 — capabilities column

**Files:**
- Create: `supabase/migrations/012_agent_capabilities.sql`

- [ ] **Step 1: Write the migration**

```sql
-- Capability bundles replace per-tool filtering (pydantic-ai v2 architecture).
-- Additive: old code ignores this column, so apply to prod before the deploy.
ALTER TABLE agents ADD COLUMN IF NOT EXISTS capabilities text[] NOT NULL DEFAULT '{}';

UPDATE agents SET capabilities = ARRAY['core','web','calendar','memory','obsidian']
WHERE slug = 'claw-main';

UPDATE agents SET capabilities = ARRAY['core','calendar','memory','workout']
WHERE slug = 'workout-coach';

-- The tools column stays until this deploy is verified, then drops in a
-- follow-up migration. Do not write to it after this point.
```

- [ ] **Step 2: Commit** `feat(db): migration 012 agent capabilities column + backfill`. Do NOT run against prod — that happens at rollout, before merge.

### Task A3: Factory reads capabilities; graceful end strategy

**Files:**
- Modify: `src/jordan_claw/agents/factory.py`, `src/jordan_claw/db/agents.py` (AgentConfig gains `capabilities: list[str]`)
- Test: `tests/test_agents.py`, `tests/test_capabilities.py`

- [ ] **Step 1: Extend AgentConfig** — add `capabilities: list[str] = []` to the Pydantic model in `db/agents.py`, and include the column in the select in `get_agent_config`.

- [ ] **Step 2: Write the failing tests** — update `test_build_agent_uses_db_config` and `test_build_agent_skips_unknown_tools` in tests/test_agents.py: fake configs now carry `capabilities=["core","web"]` (expect `{"current_datetime","search_web","fetch_article"}` sent to the model) and `capabilities=["core","nonexistent"]` (expect `{"current_datetime"}`). Keep `tools=[...]` fields in the fakes but they must have NO effect. Add to tests/test_capabilities.py a FunctionModel-based test that a `graceful` agent still completes a plain run (guards the end_strategy flip at construction level).

- [ ] **Step 3: Implement in factory.py**

```python
    groups = resolve_capabilities(config.capabilities)

    agent = Agent(
        config.model,
        instructions=system_prompt,
        capabilities=[*groups, ProcessHistory(trim_history_processor)],
        deps_type=AgentDeps,
    )
```

Removals: `_make_tool_filter`, the `BASE_TOOLSET.filtered(...)` call, the unknown-tool warning loop (the registry logs unknowns now), the `toolsets=` arg, the `end_strategy="early"` pin and its comment. `trim_history_processor` and `db_messages_to_history` unchanged. `src/jordan_claw/tools/__init__.py` keeps registering `BASE_TOOLSET` until nothing imports it — check importers (`grep -rn "BASE_TOOLSET" src/ tests/`); once factory no longer uses it, delete it and have `tools/__init__.py` just re-export the functions.

- [ ] **Step 4: Run** `uv run pytest tests/test_agents.py tests/test_capabilities.py tests/test_gateway.py -q` → all pass. **Step 5: Commit** `feat(agents): agents built from capability bundles; adopt graceful end strategy`

### Task A4: Tool-alongside-output semantics test

**Files:** Test: `tests/test_capabilities.py`

- [ ] **Step 1:** Add a FunctionModel test where the model returns a tool call AND final text in one response; assert the tool executed (side-effect flag flipped) under `graceful`. This documents the behavior change we accepted. Run, commit `test: document graceful end-strategy tool execution semantics`.

---

## Phase B: Event-driven triggers

### Task B1: Migration 013 — event triggers, watcher cursors, run_kind values

**Files:**
- Create: `supabase/migrations/013_event_triggers.sql`

- [ ] **Step 1:**

```sql
CREATE TABLE IF NOT EXISTS event_triggers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid REFERENCES organizations(id),
    source text NOT NULL,
    name text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    agent_slug text NOT NULL,
    prompt_template text NOT NULL,
    filter jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_event_triggers_source ON event_triggers(source) WHERE enabled;

CREATE TABLE IF NOT EXISTS watcher_cursors (
    source text PRIMARY KEY,
    cursor jsonb NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- run_kind gains 'event' and 'voice' (checked constraint, see 006)
ALTER TABLE usage_events DROP CONSTRAINT usage_events_run_kind_check;
ALTER TABLE usage_events ADD CONSTRAINT usage_events_run_kind_check
    CHECK (run_kind IN ('user_message','proactive','memory_extract','eval','event','voice'));

-- Proof trigger: notable inbound email -> claw-main summary
INSERT INTO event_triggers (org_id, source, name, agent_slug, prompt_template)
VALUES (
    '1408252a-fd36-4fd3-b527-3b2f495d7b9c',
    'fastmail-email',
    'inbound_email_review',
    'claw-main',
    'New email received. From: {from}. Subject: {subject}. Preview: {snippet}. If this needs Jordan''s attention, summarize it in one or two sentences and say why it matters. If it is routine or automated noise, reply with exactly NOTHING_TO_SEND.'
);
```

Constraint-name check step: `ALTER ... DROP CONSTRAINT` needs the real auto-generated name; verify with a query in the SQL editor at apply time (`select conname from pg_constraint where conrelid = 'usage_events'::regclass and contype='c';`) and adjust if Postgres named it differently. Note this in the migration as a comment. NOTE: after creating tables, PostgREST needs a schema-cache reload (`NOTIFY pgrst, 'reload schema';` — append it to the migration).

- [ ] **Step 2:** Add `EVENT = "event"` and `VOICE = "voice"` to `RunKind` in `src/jordan_claw/analytics/types.py`. Commit `feat(db): migration 013 event triggers + run_kind event/voice`.

### Task B2: Webhook endpoint + trigger pipeline

**Files:**
- Create: `src/jordan_claw/events/__init__.py`, `src/jordan_claw/events/pipeline.py`, `src/jordan_claw/db/event_triggers.py`
- Modify: `src/jordan_claw/main.py` (route), `src/jordan_claw/config.py` (`webhook_secret: str`, `app_token: str`, `fastmail_api_token: str = ""` — pydantic-settings)
- Test: `tests/test_event_pipeline.py`

- [ ] **Step 1: Failing tests** — pipeline unit tests: (a) trigger matching by source + enabled, (b) `render_prompt` fills `{from}`/`{subject}` placeholders and leaves unknown keys harmless (use `str.format_map` with a defaulting dict), (c) NOTHING_TO_SEND suppresses delivery, (d) webhook route returns 401 without `X-Claw-Secret`, 202 with it (FastAPI TestClient, agent run mocked).

- [ ] **Step 2: Implement.** `db/event_triggers.py`: `get_triggers(db, source)` (select enabled by source), `get_cursor/save_cursor`. `events/pipeline.py`:

```python
class SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_prompt(template: str, payload: dict) -> str:
    return template.format_map(SafeDict(payload))


async def process_event(db, *, source: str, payload: dict) -> int:
    """Run every enabled trigger for source against the payload. Returns runs started."""
```

`process_event` loads triggers, and for each: build agent via existing `build_agent` (org from trigger row), run through `run_agent_instrumented` (`run_kind=RunKind.EVENT`, `channel="webhook"`, `schedule_name=trigger.name`), suppress delivery when output strips to `NOTHING_TO_SEND` (reuse the sentinel handling pattern from `proactive/executors.py` — read it first and reuse its helper if importable), otherwise send via the same Telegram send used by proactive messages, and log to `proactive_messages` or a plain structlog line (decide by what executors.py does; mirror it). Route in main.py:

```python
@app.post("/webhooks/{source}", status_code=202)
async def receive_webhook(source: str, request: Request):
    if request.headers.get("X-Claw-Secret") != settings.webhook_secret:
        raise HTTPException(status_code=401)
    payload = await request.json()
    asyncio.create_task(process_event(app.state.db, source=source, payload=payload))
    return {"accepted": True}
```

(Background task, 202 immediately — webhook callers must never wait on an agent run. Track the task like `_fire_save` does in agent_runner to avoid GC.)

- [ ] **Step 3: Run tests, commit** `feat(events): webhook surface + event trigger pipeline`

### Task B3: Fastmail watcher

**Files:**
- Create: `src/jordan_claw/events/fastmail.py`
- Modify: `src/jordan_claw/proactive/scheduler.py` + `executors.py` (new task type `fastmail_watch`), migration 013 gains its schedule seed (add before applying): `('...org...', 'fastmail_watch', '*/5 * * * *', 'America/Chicago', 'fastmail_watch', '{}')`
- Test: `tests/test_fastmail_watcher.py`

- [ ] **Step 1: JMAP probe (manual, needs FASTMAIL_API_TOKEN from Jordan).** `curl -s -H "Authorization: Bearer $TOKEN" https://api.fastmail.com/jmap/session | jq '.apiUrl, .accounts'` — record apiUrl + account id shape. If the token isn't available yet, build against the documented JMAP core shapes and mark the integration test skipped-pending-token.

- [ ] **Step 2: Failing tests** — with httpx mocked (respx or monkeypatched client): first poll with empty cursor stores newest email id without firing (no backfill storm); subsequent poll with 2 new emails calls `process_event` twice with `{from, subject, snippet}` payloads; cursor advances.

- [ ] **Step 3: Implement** `poll_fastmail(db, settings)`: JMAP `Email/query` sorted by `receivedAt desc`, filter `after` cursor timestamp, then `Email/get` for `from/subject/preview`; map to payload; call `process_event(db, source="fastmail-email", payload=...)` per email; save cursor (latest receivedAt + id). Executor branch: task type `fastmail_watch` → `poll_fastmail`; skip silently when `settings.fastmail_api_token` is empty (log once).

- [ ] **Step 4: Run tests, commit** `feat(events): fastmail JMAP watcher on 5-minute schedule`

---

## Phase C: Voice ingestion + classifier routing

### Task C1: Classifier

**Files:**
- Create: `src/jordan_claw/gateway/classifier.py`
- Test: `tests/test_classifier.py`

- [ ] **Step 1: Failing tests** — with `TestModel(custom_output_args=...)`: workout-ish transcript routes to workout-coach; generic routes to claw-main; low confidence falls back to claw-main; unknown slug in output falls back to claw-main.

- [ ] **Step 2: Implement**

```python
class RouteDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    agent_slug: str
    confidence: float = Field(ge=0.0, le=1.0)

CLASSIFIER_MODEL = "anthropic:claude-haiku-4-5-20251001"
CONFIDENCE_FLOOR = 0.6
DEFAULT_AGENT = "claw-main"


def build_classifier(agent_catalog: str) -> Agent[object, RouteDecision]:
    return Agent(
        CLASSIFIER_MODEL,
        instructions=(
            "Route the user's utterance to exactly one agent. Available agents:\n"
            f"{agent_catalog}\n"
            "Pick workout-coach only for training, exercise, fitness logging, or "
            "physical-activity planning. Everything else goes to claw-main."
        ),
        output_type=RouteDecision,
    )


async def classify(db, transcript: str, org_id: str) -> str:
    ...  # catalog built from agents table slugs + CAPABILITY_REGISTRY descriptions;
         # run classifier via run_agent_instrumented? NO — direct agent.run with its own
         # small logfire span; classification is not a user-visible agent run. Wrap
         # in try/except: any failure returns DEFAULT_AGENT.
```

Catalog source: `agents` table (slug, name) joined with each agent's capability descriptions via `CAPABILITY_REGISTRY` — the Phase A payoff. Failure mode is always claw-main, never an error to the user.

- [ ] **Step 3: Run tests, commit** `feat(gateway): voice route classifier`

### Task C2: Transcription + /voice endpoint

**Files:**
- Create: `src/jordan_claw/gateway/voice.py`
- Modify: `src/jordan_claw/main.py`
- Test: `tests/test_voice_endpoint.py`

- [ ] **Step 1: Failing tests** — 401 without bearer `CLAW_APP_TOKEN`; happy path with transcription + classifier + gateway mocked returns `{"transcript", "agent_slug", "reply"}`; transcription failure → 502 with clear detail.

- [ ] **Step 2: Implement.** `transcribe(audio_bytes, filename, settings)` posts multipart to `https://api.openai.com/v1/audio/transcriptions` (`model=whisper-1`, existing `openai_api_key`, httpx, 60s timeout). Route:

```python
@app.post("/voice")
async def voice_message(request: Request, file: UploadFile):
    _require_bearer(request, settings.app_token)
    transcript = await transcribe(await file.read(), file.filename, settings)
    slug = await classify(db, transcript, settings.default_org_id)
    reply = await handle_app_message(db, org_id=..., agent_slug=slug, text=transcript,
                                     channel="app-voice", run_kind=RunKind.VOICE)
    return {"transcript": transcript, "agent_slug": slug, "reply": reply}
```

`handle_app_message` is a thin variant of the gateway path: reuse `gateway/router.py`'s flow (conversation upsert per channel, memory context, instrumented run, memory extraction kickoff) — read router.py first; extract shared logic into a helper ONLY if the reuse is awkward otherwise (minimal blast radius; duplication of 15 lines beats a refactor here if router is tangled). Voice replies return over HTTP; no Telegram delivery.

- [ ] **Step 3: Run tests, commit** `feat(gateway): /voice endpoint with whisper transcription and routed reply`

---

## Phase D: Verification + PR

- [ ] Full suite `uv run pytest -q`; ruff check on changed files only (pre-existing 18 findings stay out of scope).
- [ ] PR body: summary per phase; rollout order (migrations 012+013 in prod SQL editor FIRST — includes the pg_constraint name check and `NOTIFY pgrst, 'reload schema'`); secrets checklist (FASTMAIL_API_TOKEN, CLAW_WEBHOOK_SECRET, CLAW_APP_TOKEN in Infisical AND Railway service env); post-deploy verification: both bots respond, `curl -X POST .../webhooks/test -H "X-Claw-Secret: ..."` → 202 and a usage_events row with run_kind='event' (after seeding a test trigger), voice curl with a sample m4a → transcript + reply JSON, watch trigger fire on a real email within 5 minutes.
- [ ] Post-merge deploy watch per deploy-verify skill; evidence-based done reporting throughout.
- [ ] Follow-up (not this PR): drop `agents.tools` column once verified; deferred-loading pilot for the obsidian bundle (needs a measurement plan); Telegram voice-note routing through the same classifier; Flutter auth replacing CLAW_APP_TOKEN.

## Self-review notes (writing-plans checklist)

- All 16 tools covered by exactly one group (6+2+2+2+3+1); registry test enforces it.
- Migration 013 respects both standing DB lessons: check-constraint extension for run_kind, PostgREST schema reload after new tables.
- No new Python dependencies anywhere (httpx already present; no openai sdk, no jmapc).
- Type consistency: `resolve_capabilities` returns `list[ToolGroup]`; factory consumes it; classifier returns str slug consumed by `handle_app_message`.
- Known uncertainty flagged inline: AbstractCapability field shape (A1 Step 1 verifies), JMAP session shapes (B3 Step 1 probes), usage_events constraint name (checked at apply time).
