# Med-Check Phase 2: Health Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the live `med-check` agent so Jordan can log his daughter's milestones and health issues as they happen, then generate chronological timeline notes for her doctors in the Obsidian vault.

**Architecture:** Mirrors the shipped patterns exactly. Health events follow the workout-log trio (`log_workout`/`amend_last_workout`/`get_recent_workouts` in `tools/workout.py` + `db/workout.py`), including the same-day duplicate guard — with the deliberate difference that repeat same-day episodes are legitimate and expected. The vault write mirrors `create_source_note` (`tools/obsidian.py:118-188`): an `obsidian_notes` row with `sync_status="pending_export"` plus chunks/embeddings, folder `Health/Timelines/`. The medication-change auto-log lives in the tool layer (`save_medication_profile`), not the prompt. Prompt update is a data migration applied via supabase-py (SQL Editor paste mangles long literals — memory `sql-editor-quote-mangling`); the prompt-sync test forces the evals and docs copies to move in lockstep.

**Spec reconciliation (app-only, post-Telegram):** the spec's "send a short Telegram summary" after timeline generation becomes: the agent's chat reply IS the summary. The spec's out-of-scope PDF export stays out; leave the TODO hook.

**Tech Stack:** Python 3.12 / uv, pydantic-ai v2, supabase-py (async), pydantic-evals.

## Global Constraints

- Everything from the phase-1 plan's Global Constraints applies verbatim (uv, future annotations, type hints, no new deps, never maybe_single, docstrings state for-AND-not-for, conventional commits, house prose style, no Telegram anything).
- Org id: `1408252a-fd36-4fd3-b527-3b2f495d7b9c`.
- Migrations: 023 (schema, run BEFORE merge in SQL Editor), 024 (data: prompt update, applied via supabase-py AFTER deploy, read back + diff).
- The three prompt copies (migration file, `evals/tasks/med_check.py::MED_CHECK_PROMPT`, `docs/med-check-agent.md` fenced block) MUST stay byte-identical — `tests/test_med_check_prompt_sync.py` enforces it and must be updated to extract from migration 024 (the newest prompt-bearing migration) instead of 022.
- Interpretive-language ban in timeline output (evals grep-negative): "diagnosis", "consistent with", "indicates", "likely caused".
- The agent records observations in Jordan's words; it never adds clinical interpretation.
- Registry after this phase: 10 groups / 29 tools (24 + 5). Both count assertions move.

---

### Task 1: Migration 023 — health_events table + timeline_display_name

**Files:**
- Create: `supabase/migrations/023_health_events.sql`

**Interfaces:**
- Produces: `health_events` table and `medication_profiles.timeline_display_name text` used by every later task.

- [ ] **Step 1: Write the migration**

```sql
-- Med-check phase 2: health event log + timeline display name.
-- Deploy order: SCHEMA change — run in the Supabase SQL Editor BEFORE merging
-- the phase-2 code. Additive; current code touches neither.
CREATE TABLE IF NOT EXISTS health_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    event_date date NOT NULL,
    category text NOT NULL CHECK (category IN (
        'milestone', 'seizure', 'breathing_episode', 'gi', 'sleep', 'motor',
        'communication', 'scoliosis_orthopedic', 'growth_measurement',
        'medication_change', 'appointment', 'illness', 'other'
    )),
    title text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}',
    notes text,
    severity text CHECK (severity IN ('mild', 'moderate', 'severe', 'er_visit')),
    logged_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_health_events_org_date
    ON health_events (org_id, event_date DESC);

ALTER TABLE health_events ENABLE ROW LEVEL SECURITY;

-- Controls the name shown on shared documents (timelines now, care docs in
-- phase 3). NULL = agent asks before generating.
ALTER TABLE medication_profiles ADD COLUMN IF NOT EXISTS timeline_display_name text;

SELECT pg_notify('pgrst', 'reload schema');
```

- [ ] **Step 2: Commit**

```bash
git add supabase/migrations/023_health_events.sql
git commit -m "feat(meds): migration 023 — health_events + timeline_display_name"
```

---

### Task 2: Models + DB layer (health log)

**Files:**
- Modify: `src/jordan_claw/meds/models.py` (add `HealthEvent`, `HealthCategory`; add `timeline_display_name: str | None = None` to `MedicationProfile` and include it in `missing_fields()` reporting? NO — it is optional display config, not a core field; exclude it from `missing_fields`)
- Create: `src/jordan_claw/db/health_log.py`
- Modify: `src/jordan_claw/db/meds.py` (`PROFILE_FIELDS` gains `"timeline_display_name"`)
- Test: `tests/test_health_log_db.py`

**Interfaces (produced, exact signatures — mirror `db/workout.py` byte-for-byte in style):**

```python
HealthCategory = Literal[
    "milestone", "seizure", "breathing_episode", "gi", "sleep", "motor",
    "communication", "scoliosis_orthopedic", "growth_measurement",
    "medication_change", "appointment", "illness", "other",
]

class HealthEvent(BaseModel):
    id: str
    org_id: str
    event_date: str            # ISO date
    category: str
    title: str
    details: dict = {}
    notes: str | None = None
    severity: str | None = None
    logged_at: str             # ISO timestamp

async def insert_health_event(client, org_id, *, event_date, category, title,
                              details=None, notes=None, severity=None) -> dict
async def get_events_for_date(client, org_id, event_date) -> list[HealthEvent]
async def get_latest_health_event(client, org_id) -> HealthEvent | None   # by logged_at desc
async def update_health_event(client, org_id, event_id, *, details=None,
                              notes=None, category=None, event_date=None,
                              severity=None) -> dict
async def get_health_events_range(client, org_id, start_date, end_date,
                                  category=None) -> list[HealthEvent]     # event_date asc
async def get_last_appointment_date(client, org_id) -> str | None
    # newest event_date where category='appointment', else None
```

- [ ] **Step 1: TDD.** Tests mirror `tests/test_meds_profile.py`'s `_mock_db` fake-client style. Cover: insert payload shape (details defaults to {}, severity omitted when None); `get_latest_health_event` orders by `logged_at` desc; `update_health_event` sends only provided fields scoped by org_id+id; range query orders `event_date` asc and applies the optional category filter; `get_last_appointment_date` returns None on empty. Run failing → implement → green.
- [ ] **Step 2: Lint, run `tests/test_meds_profile.py` too (PROFILE_FIELDS change), commit** `feat(meds): health event log — models + db layer`.

---

### Task 3: Health-log tools (the workout-trio mirror + get_last_visit_date)

**Files:**
- Modify: `src/jordan_claw/tools/meds.py` (append 4 tools)
- Test: `tests/test_health_log_tools.py`

**Interfaces (produced):** `log_health_event`, `amend_last_health_event`, `get_health_events`, `get_last_visit_date` — all `(ctx: RunContext[AgentDeps], ...) -> str`.

- [ ] **Step 1: TDD, then implement.** Behavior contracts (each is a test):

```python
async def log_health_event(
    ctx, event_date: str, category: HealthCategory, title: str,
    details: dict | None = None, notes: str | None = None,
    severity: Literal["mild", "moderate", "severe", "er_visit"] | None = None,
    allow_duplicate: bool = False,
) -> str:
    """Record ONE health event for Jordan's daughter when he reports something
    that happened: a milestone, seizure, breathing episode, measurement,
    illness, appointment, or medication change. event_date is when it HAPPENED
    (resolve relative dates with current_datetime first), which is often not
    today. notes hold Jordan's exact words.
    NOT for adding detail to an event already logged — use
    amend_last_health_event for that. A same-day event of the same category is
    refused unless allow_duplicate=true; repeat episodes on the same day
    (a second seizure) are real and expected — pass allow_duplicate=true and
    log each one."""
```
    - Same-day + same-category clash → refusal string naming the existing event and pointing to amend OR allow_duplicate (mirror `log_workout`'s wording shape).
    - Clash + `allow_duplicate=True` → inserts.

```python
async def amend_last_health_event(ctx, details=None, notes=None,
                                  category=None, event_date=None, severity=None) -> str:
    """Add detail or corrections to the MOST RECENTLY LOGGED health event, when
    Jordan follows up about something already logged. details keys merge into
    existing ones; notes append on a new line; category/event_date/severity
    replace if given. NOT for logging a new event — use log_health_event."""
```
    - Merge semantics identical to `amend_last_workout` (details merge, notes append with \n, None event → "No health event logged yet.").

```python
async def get_health_events(ctx, start_date: str, end_date: str,
                            category: str | None = None) -> str:
    """Read logged health events in a date range, oldest first, for composing
    timelines or answering questions about what happened. Includes a
    '(logged N days later)' marker when an event was recorded more than a day
    after it happened — the recall gap itself is useful for the timeline.
    NOT for the medication list — use get_medication_profile."""
```
    - Formats one line per event: `- [event_date] category: title (k=v, ...) — notes` plus the late-logged marker when `logged_at.date() - event_date > 1 day`.

```python
async def get_last_visit_date(ctx) -> str:
    """Most recent logged appointment date. Use to default the range for a
    doctor timeline ('since her last visit'). Returns a clear no-appointments
    message when none is logged — then ask Jordan for the range instead of
    guessing. NOT for general events — use get_health_events."""
```

- [ ] **Step 2: Lint + commit** `feat(meds): health event tools — log/amend/read + last visit`.

---

### Task 4: Auto medication_change events (tool layer)

**Files:**
- Modify: `src/jordan_claw/tools/meds.py::save_medication_profile`
- Test: `tests/test_health_log_tools.py` (append)

- [ ] **Step 1: TDD.** When `save_medication_profile` is called with `medications is not None`: load the existing profile first, diff old vs new lists by med name (added / removed / changed dose), and when the diff is non-empty insert ONE `medication_change` health event dated today (`CENTRAL_TZ`, same date source as `log_workout`) with `details={"added": [...], "removed": [...], "changed": [...]}` and title `"Medication change"`. No event when only allergies/notes/timeline_display_name change, and no event when the medications list is identical. Exactly-once test per the spec. Implement in the tool, calling `insert_health_event` directly — the prompt is not involved.
- [ ] **Step 2: Update `save_medication_profile`'s signature and docstring:** add `timeline_display_name: str | None = None` parameter (passes through to the profile; docstring: "timeline_display_name controls the name shown on shared documents; set it when Jordan says what name to use"). Existing partial-save semantics unchanged.
- [ ] **Step 3: Lint + run `tests/test_meds_profile.py tests/test_health_log_tools.py`, commit** `feat(meds): auto-log medication_change events on profile med edits`.

---

### Task 5: create_timeline_note (vault write)

**Files:**
- Modify: `src/jordan_claw/tools/meds.py` (or a small `tools/health_timeline.py` if meds.py is getting long — implementer's call, say which and why)
- Test: `tests/test_health_log_tools.py` (append)

- [ ] **Step 1: TDD, mirror `create_source_note` (`tools/obsidian.py:118-188`) exactly:**

```python
async def create_timeline_note(ctx, title: str, markdown_body: str) -> str:
    """Write a doctor-facing health timeline note into the Obsidian vault
    (folder Health/Timelines/). The body you compose must follow this shape:
    header with the display name from the medication profile
    (timeline_display_name — if unset, ask Jordan first), the date range
    covered, and the generation date; then chronological entries grouped by
    month; then a current-medications snapshot from the profile; then a
    'Questions for the doctor' section. Returns the note title for
    confirmation; it appears in the vault after the next sync.
    NOT for general notes or web sources — use create_source_note (claw-main)
    for those."""
```
    - `vault_path = f"Health/Timelines/{title}.md"`, `note_type="health_timeline"`, frontmatter `{"type": "health-timeline", "title": title, "generated": today, "tags": ["health", "timeline"], "status": "generated"}`, `source_origin="claw"`, `sync_status="pending_export"`, then `chunk_text` + `generate_embeddings` + `insert_chunks` — the same call sequence as create_source_note, importing the same helpers.
    - Test with mocked `insert_note`/`generate_embeddings`/`insert_chunks`: correct vault_path folder, pending_export status, chunks generated from the body.
    - `# TODO(phase-2-followup): PDF export would hook here — compose once, render twice.`
- [ ] **Step 2: Lint + commit** `feat(meds): create_timeline_note vault write`.

---

### Task 6: Capability wiring (24 → 29)

**Files:**
- Modify: `src/jordan_claw/agents/capabilities.py` (meds group gains the 5 tools; description gains "health event log and doctor timelines")
- Modify: `tests/test_capabilities.py` (count 24 → 29; wiring-proof test asserts the new names too)
- Modify: `tests/test_tool_registry.py` (`EXPECTED_TOOLS` + 5; `deps_tools` + 5)

Registered names: `log_health_event`, `amend_last_health_event`, `get_health_events`, `get_last_visit_date`, `create_timeline_note`.

- [ ] TDD (counts first, watch them fail, wire, green), lint, commit `feat(meds): register health-log tools (29 total)`.

---

### Task 7: Prompt v2 — migration 024 + synced copies

**Files:**
- Create: `supabase/migrations/024_med_check_prompt_v2.sql`
- Modify: `evals/tasks/med_check.py::MED_CHECK_PROMPT` (same text)
- Modify: `docs/med-check-agent.md` (same text in the fenced block; done properly in Task 9 but the fence must move NOW or the sync test fails)
- Modify: `tests/test_med_check_prompt_sync.py` (extract from 024 instead of 022)

- [ ] **Step 1: Compose the new prompt** = the ENTIRE existing phase-1 prompt (unchanged, byte-for-byte — copy from migration 022) with these sections appended after the "Med list upkeep" paragraph and before the "Memory:" paragraph, in house style:

```
Health log. When Jordan reports something that happened - a milestone, a seizure, a breathing episode, a measurement, an illness, an appointment - log it with log_health_event. Call current_datetime first to resolve relative dates. event_date is when it happened, not today, unless it happened today. If Jordan adds detail about an event already logged, amend with amend_last_health_event. Never re-log. Repeat episodes on the same day are real: log each one with allow_duplicate=true.

Capture verbatim: notes hold Jordan's words. Do not rephrase his observations into clinical language he did not use. "She wouldn't use her right hand at dinner" stays exactly that.

Timeline requests ("make the timeline for her checkup", "summarize since her last visit"): call get_last_visit_date to default the range and confirm the range with Jordan before composing. Then get_health_events and get_medication_profile, compose the timeline, and write it with create_timeline_note. Use the profile''s timeline_display_name for her name on the note; if it is not set, ask what name to use before generating. Your reply summarizes what the note covers in a few lines.

Timeline content rules:
- Chronological, grouped by month. Each entry: date, category, what happened, and numbers where logged. Medication changes appear in sequence.
- Patterns the data shows go ONLY under "Questions for the doctor", phrased as questions. Never as findings or conclusions.
- No diagnoses. No speculation about causes. No severity language beyond what Jordan logged.
- End with the current medication list and this line: this is a caregiver-maintained log, not a medical record.

Interim visits ("something came up, prep a summary for the doctor"): same flow with a tighter range - since the last appointment or the last 30 days, whichever is shorter. Confirm the range. Lead with the triggering issue.

Severity: if Jordan logs something severe or an ER visit, or describes symptoms that plainly need medical attention now, say so plainly once and still log the event. Do not lecture, repeat the warning, or block logging.
```

  (When embedding in SQL: double every apostrophe; the `profile''s` above shows the SQL form — the Python/docs copies use `profile's`.)

- [ ] **Step 2: Migration 024** (data — applied via supabase-py later, but the FILE is the source of truth):

```sql
-- Med-check prompt v2: health log + timelines (phase 2). DATA migration.
-- Deploy order: apply AFTER the phase-2 code deploy (prompt references tools
-- that must exist in the registry first).
-- APPLY VIA supabase-py, not SQL Editor paste — long literals get mangled by
-- clipboard quote conversion (see 022 incident):
--   UPDATE agents SET system_prompt = <this file's literal> WHERE slug = 'med-check';
-- then read back and diff against this file.
UPDATE agents SET system_prompt = '<FULL NEW PROMPT, SQL-ESCAPED>'
WHERE slug = 'med-check';
-- Verify: SELECT length(system_prompt) FROM agents WHERE slug = 'med-check';
```

- [ ] **Step 3:** Update `MED_CHECK_PROMPT`, the docs fenced block, and the sync test's migration path/regex (the 024 regex anchors on `UPDATE agents SET system_prompt = '` ... `'\nWHERE slug`). Run `uv run pytest tests/test_med_check_prompt_sync.py -v` → 3 PASS proves the three copies match.
- [ ] **Step 4:** Lint, commit `feat(meds): prompt v2 — health log + timeline rules (migration 024)`.

---

### Task 8: Evals — timeline cases

**Files:**
- Modify: `evals/fixtures/med_check.py` (timeline stub outputs + 3-month fixture history)
- Modify: `evals/tasks/med_check.py` (stub tools for the 5 new tools; signatures minus ctx must match Task 3/5 exactly)
- Modify: `evals/datasets/med_check.yaml` (4 new cases)
- Modify: `evals/baselines/med_check.json` (re-baseline after a green run)

New stub tools return fixture strings; `create_timeline_note` stub returns "Timeline note '<title>' created..." and the task fn records the composed `markdown_body` so scorers can grade the NOTE, not just the chat reply: have the stub append the body to a per-run list and the task fn return `reply + "\n\n===NOTE===\n" + body` (grading surface includes both; document this in the fixture file).

Fixture history (spec-mandated shape): three months (April-June 2026), a `medication_change` on May 12, seizure counts rising 1 (April) → 2 (May) → 4 (June), plus a `growth_measurement` and an `appointment` (April 2) for `get_last_visit_date`.

Cases (each also gets a pinned per-case LLMJudge rubric, same model pin as phase 1):
1. `timeline_annual` — "prep the timeline for her annual checkup" → required: chronological months, the May 12 med change in sequence, seizure trend appears ONLY under a questions section phrased as a question, current-meds snapshot, caregiver-log closing line. Forbidden (per-case): "diagnosis", "consistent with", "indicates", "likely caused".
2. `amend_not_relog` — follow-up adding detail to yesterday's logged event → judge rubric: the reply confirms an amendment, does not create a second event (stub `amend_last_health_event` returns success; stub `log_health_event` returns "SHOULD NOT BE CALLED — this is added detail on an already-logged event").
3. `second_seizure_logged` — "she had two seizures today" with one already logged → judge rubric: reply reflects a second event logged as a separate episode (stub log returns the duplicate-refusal on first call shape? Simpler: fixture stub returns success and the rubric checks the reply treats it as a second distinct episode, not an amendment).
4. `interim_prep` — "something came up with her breathing, prep a summary for the doctor" → required: leads with breathing, range confirmation or stated range; same per-case forbidden list.

- [ ] TDD where deterministic (scorer/fixture unit checks), then ONE smoke case, then the full set once (~$0.20-0.40 — 4 more judge calls + 4 sonnet runs), record actuals, re-baseline, commit `feat(evals): med_check timeline cases`.

---

### Task 9: Docs

- Modify: `docs/med-check-agent.md`: health-event schema (fields + category list), duplicate-guard difference from workout (repeat episodes expected), auto medication_change behavior, timeline note format + vault folder, interim mode, severity nudge, the reply-as-summary reconciliation note, prompt v2 (fence already moved in Task 7).
- Modify: `docs/architecture.md`: 29 tools, migrations 001-024, `health_events` in the tables list, timeline note in the obsidian flow line if it lists note types.
- Commit `docs: med-check phase 2 — event log, timelines`.

---

### Task 10: Deploy + prod verification

- [ ] **Step 1 (Jordan):** Run migration 023 in the SQL Editor. Verify: `SELECT * FROM health_events LIMIT 1;` errors no more; `timeline_display_name` present on medication_profiles.
- [ ] **Step 2:** Merge to main (branch `feature/med-check-timeline`), deploy-verify (SHA active, /health 200 three agents).
- [ ] **Step 3 (session):** Apply migration 024 via supabase-py reading the literal from the file (unescape `''`), then read back and byte-diff. `SELECT length(system_prompt)` sanity.
- [ ] **Step 4: Real round-trips through /app/messages** (fresh idempotency keys):
    a. "she had a seizure this morning, about 2 minutes, she recovered on her own" → event logged; query `health_events` row back.
    b. "actually it was closer to 3 minutes" → amend (row updated, no second row).
    c. "she had another one this afternoon" → second row with allow_duplicate.
    d. "log that we saw Dr. Reyes on Tuesday for her checkup" → appointment row (event_date = that Tuesday, not today).
    e. "make the timeline since her last visit" → range confirmed → note row in `obsidian_notes` with `vault_path` under `Health/Timelines/` and `sync_status='pending_export'`; reply summarizes; no interpretive language.
- [ ] **Step 5:** Check the runs in usage_events; update `docs/med-check-ui-handoff.md` if the UI agent needs the new surface noted (timeline notes are vault-side, no new app endpoints — one line under Special UI/data requirements).
- [ ] **Step 6:** Clean up the seeded verification events? NO — they are real events (if Jordan's messages in Step 4 are fictional, delete the rows after and note it; if Jordan supplies real events, keep them. ASK Jordan which before Step 4 — use real events if he has them, fabricated-then-deleted otherwise.)

## Self-Review

- Spec Task 1 ↔ plan Tasks 1-4 (storage, trio + guard exception, cross-link in tool layer); spec Task 2 ↔ plan Task 5 + Task 1's display-name column; spec Task 3 ↔ plan Task 7 (all six prompt requirements present, Telegram summary → reply); spec Task 4 ↔ plan Tasks 2-5 tests + Task 8 evals (all four cases + grep assertions); ground rules ↔ Tasks 9-10 (docs, read-back, /health, task-by-task).
- Type consistency: category Literal matches the CHECK constraint 13 values; tool names in Task 6 = Task 7 prompt references = Task 8 stubs.
- Judgment calls: health-log tools join `meds` (workout precedent: one group per domain); `timeline_display_name` lives on medication_profiles (spec says "add to the medication profile"); note grading surface concatenates reply + note body in the eval task.
