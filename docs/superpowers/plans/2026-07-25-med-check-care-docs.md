# Med-Check Phase 3: Care Documents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two living documents generated from structured profile data and kept current automatically: an emergency one-pager for ER staff and first responders, and a caregiver handoff document for grandparents, respite care, and school nurses.

**Architecture:** A `care_profiles` sibling of `medication_profiles` (same partial-save pattern) holds everything the documents need beyond meds. Documents are composed by the model and written through the phase-2 vault mechanism with date-versioned titles (spec's sanctioned fallback; also sidesteps the `unique(org_id, vault_path)` 409 on regeneration). A `care_documents` table stores, per doc_type, the source snapshot hash so `check_care_docs_current()` returns current | stale | never_generated deterministically. Staleness automation is two-layer: a prompt rule (one-line offer after profile saves) and a weekly scheduler executor that publishes to the app briefing section ONLY when something is stale (`publish_proactive_message`, the post-Telegram delivery path Jordan confirmed surfaces in the Flutter app).

**Spec reconciliations (decided):** "messages Jordan" = app briefing artifact (pull-only until APNs). Overwrite-on-regenerate = date-versioned titles + newest tracked in `care_documents` (spec's own fallback path). `include_photo_path` = SKIPPED (vault notes are markdown text through `insert_note`; no image-embedding mechanism exists — spec says skip rather than force). Handoff doc's snapshot hash covers the care profile only; the emergency doc's covers care profile + medication profile (matches the spec's own unit-test expectation).

**Tech Stack:** Python 3.12 / uv, pydantic-ai v2, supabase-py (async), croniter scheduler (existing), pydantic-evals.

## Global Constraints

- Phase-1/2 global constraints apply verbatim (uv, future annotations, type hints, no new deps, never maybe_single, for-AND-not-for docstrings, conventional commits, house style, no em dashes in new prose, no Telegram).
- Org id: `1408252a-fd36-4fd3-b527-3b2f495d7b9c`.
- Migrations: **025** (schema: care_profiles + care_documents + seeded critical_flags row — run in SQL Editor BEFORE merge), **026** (data: weekly schedule seed — run AFTER deploy, supabase-py fine), **027** (data: prompt v3 — apply via supabase-py AFTER deploy, read back + byte-diff).
- Three prompt copies stay byte-identical; `tests/test_med_check_prompt_sync.py` re-anchors on 027.
- The critical_flags QT warning may NEVER be cut, summarized away, or moved below the fold in either document. Seed text (verbatim, from spec): "Congenital Long QT — avoid QT-prolonging medications (CredibleMeds list); confirm any new drug with cardiology." (The em dash is part of the seeded DATA string, not prose — keep it.)
- Emergency one-pager body budget: ~2,500 chars, cut routine detail never safety content.
- Both documents end with a generation date and "maintained by her parents; not a medical record."
- Missing sections render as "not provided" — never silently omitted.
- Never invent or infer profile content. Intake asks one question at a time, saves each answer as it arrives, restates each saved answer in one line.
- Registry after this phase: 10 groups / 33 tools (29 + 4). Both count assertions move.
- Evals: grep assertion — the seeded QT warning string appears VERBATIM in every emergency-doc output; grep-negative "diagnosis"/"likely"/"indicates" scoped per the phase-2 `forbidden_in_note` mechanism.

---

### Task 1: Migration 025 — care_profiles + care_documents + seed

**Files:** Create `supabase/migrations/025_care_profiles.sql`

- [ ] **Step 1: Write the migration**

```sql
-- Med-check phase 3: care profile + generated-document tracking.
-- Deploy order: SCHEMA change — run in the Supabase SQL Editor BEFORE merging
-- the phase-3 code. Additive; current code touches neither table.
CREATE TABLE IF NOT EXISTS care_profiles (
    org_id uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    diagnoses jsonb NOT NULL DEFAULT '[]',
    critical_flags jsonb NOT NULL DEFAULT '[]',
    seizure_plan text,
    baselines text,
    communication text,
    routines text,
    escalation text,
    contacts jsonb NOT NULL DEFAULT '[]',
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS care_documents (
    org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    doc_type text NOT NULL CHECK (doc_type IN ('emergency', 'handoff')),
    source_hash text NOT NULL,
    note_title text NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, doc_type)
);

ALTER TABLE care_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE care_documents ENABLE ROW LEVEL SECURITY;

-- Seed the first critical flag (spec-mandated; Jordan can edit or add via the agent)
INSERT INTO care_profiles (org_id, critical_flags)
VALUES (
    '1408252a-fd36-4fd3-b527-3b2f495d7b9c',
    '["Congenital Long QT — avoid QT-prolonging medications (CredibleMeds list); confirm any new drug with cardiology."]'
)
ON CONFLICT (org_id) DO NOTHING;

SELECT pg_notify('pgrst', 'reload schema');
```

- [ ] **Step 2: Commit** `feat(meds): migration 025 — care profiles + care document tracking`

---

### Task 2: Models + DB layer (care profile + doc tracking)

**Files:** Modify `src/jordan_claw/meds/models.py`; Create `src/jordan_claw/db/care.py`; Test `tests/test_care_db.py`

**Interfaces produced (mirror db/meds.py + db/workout.py style exactly):**

```python
class CareContact(BaseModel):
    role: str          # "mom", "cardiology", "pediatrician", "pharmacy"...
    name: str
    phone: str | None = None

class CareProfile(BaseModel):
    org_id: str
    diagnoses: list[str] = []
    critical_flags: list[str] = []
    seizure_plan: str | None = None
    baselines: str | None = None
    communication: str | None = None
    routines: str | None = None
    escalation: str | None = None
    contacts: list[CareContact] = []
    def empty_sections(self) -> list[str]: ...   # every falsy section by name, all 8 tracked

CARE_PROFILE_FIELDS = ("diagnoses", "critical_flags", "seizure_plan", "baselines",
                       "communication", "routines", "escalation", "contacts")

async def get_care_profile(client, org_id) -> CareProfile | None
async def upsert_care_profile(client, org_id, **fields) -> None      # partial, non-None only
async def get_care_document(client, org_id, doc_type) -> dict | None # .limit(1), row or None
async def upsert_care_document(client, org_id, *, doc_type, source_hash, note_title) -> None
    # on_conflict="org_id,doc_type"
```

- [ ] TDD (mirror tests/test_meds_profile.py's `_mock_db`): empty_sections full/partial/none; partial upsert payload shape (allergies-analog test: seizure_plan-only save sends only org_id+seizure_plan+updated_at); care_document upsert on_conflict pair; get returns None on empty. Implement, green, ruff, commit `feat(meds): care profile + document tracking — models + db layer`.

---

### Task 3: Snapshot hash + tools

**Files:** Modify `src/jordan_claw/tools/meds.py` (4 new tools + hash helper); Test `tests/test_care_tools.py`

**Hash contract (deterministic, test-pinned):**

```python
def _care_source_hash(doc_type: str, care: CareProfile | None, meds: MedicationProfile | None) -> str:
    """sha256 over canonical JSON of the fields a doc_type is built from.
    emergency: full care profile + medications + allergies + timeline_display_name.
    handoff: full care profile + timeline_display_name only (meds appear in the
    handoff only as 'handled by her parents' unless a dose falls in care windows,
    so med edits must not flip it stale)."""
    payload = {"care": care.model_dump(exclude={"org_id"}) if care else None}
    payload["display_name"] = meds.timeline_display_name if meds else None
    if doc_type == "emergency":
        payload["medications"] = [m.model_dump() for m in meds.medications] if meds else []
        payload["allergies"] = meds.allergies if meds else None
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
```

**Tools (docstrings must state for/not-for; write them in the implementer brief style of phases 1-2):**

- `get_care_profile_tool(ctx) -> str` — profile JSON + "Empty sections: ..." report. Call before intake and before generating either document. NOT for medications (get_medication_profile).
- `save_care_profile(ctx, diagnoses=None, critical_flags=None, seizure_plan=None, baselines=None, communication=None, routines=None, escalation=None, contacts=None) -> str` — partial saves during intake, one answer at a time; contacts is list[CareContact]; lists REPLACE wholesale (read first). Never invent content. Returns "Care profile saved."
- `save_care_document(ctx, doc_type: Literal["emergency","handoff"], markdown_body: str) -> str` — writes the composed document to the vault via the phase-2 mechanism (title f"{display_name} - {'Emergency One-Pager' if emergency else 'Caregiver Handoff'} - {YYYY-MM-DD}", folder `Health/Documents/`, note_type "care_document", frontmatter type "care-document" + doc_type field, pending_export, chunks+embeddings), computes `_care_source_hash` from the CURRENT profiles at write time, upserts care_documents, returns the note title. Docstring: compose the body per the prompt's rules FIRST; this tool only writes. Also states: emergency body must fit ~2,500 chars — the tool WARNS in its return string when exceeded ("body is N chars, over the one-page budget - cut routine detail, never safety content, and rewrite") and does NOT write in that case (hard gate, deterministic).
- `check_care_docs_current(ctx) -> str` — per doc_type: never_generated | current | stale. Stale computation: stored hash != _care_source_hash(now). Stale result lists which top-level payload keys differ ONLY at the granularity we can know (recompute per-section subhashes: implement by hashing each care section separately into the payload so a dict diff names changed sections). Returns a compact report line per doc.

- [ ] TDD: hash stability (same inputs → same hash; key order irrelevant); med edit flips emergency stale but NOT handoff; care edit flips both; never_generated on empty table; budget gate refuses oversized emergency body; title versioning by date; display-name-missing → tool returns "timeline_display_name is not set - ask Jordan what name to use before generating" without writing. Implement, green, ruff, commit `feat(meds): care document tools — profile, generate, staleness`.

---

### Task 4: Capability wiring (29 → 33)

**Files:** `agents/capabilities.py` (meds group + 4: get_care_profile, save_care_profile, save_care_document, check_care_docs_current; description gains "care profile and emergency/handoff documents"), `tests/test_capabilities.py` (29 → 33 + wiring proof names), `tests/test_tool_registry.py` (EXPECTED_TOOLS + deps_tools + 4).

- [ ] TDD counts-first, wire, green, ruff, commit `feat(meds): register care-document tools (33 total)`.

---

### Task 5: Weekly staleness executor + schedule seed (migration 026)

**Files:** Modify `src/jordan_claw/proactive/executors.py` (+ EXECUTOR_MAP entry `care_docs_check`); Create `supabase/migrations/026_care_docs_check_schedule.sql`; Test `tests/test_proactive_care_docs.py`

- [ ] **Executor** (mirror `execute_weekly_training_review`'s deterministic short-circuit style): `execute_care_docs_check(db, org_id, config, settings) -> str` — computes staleness DIRECTLY via the db layer + `_care_source_hash` (no agent run, no LLM): all current → return `"NOTHING_TO_SEND"` sentinel (grep executors.py for the exact existing sentinel the scheduler honors and match it); anything stale/never_generated → return a short deterministic message ("Jessie's emergency one-pager is out of date (medications changed). Ask med-check to regenerate it." — display name from the profile, plain house style). The scheduler's existing delivery path publishes it to the app briefing.
- [ ] **Migration 026** (data, post-deploy, idempotent mirror of 018's shape):

```sql
-- Weekly care-document staleness check (phase 3). DATA migration.
-- Deploy order: run AFTER the phase-3 deploy (executor must exist).
INSERT INTO proactive_schedules (org_id, name, cron_expression, timezone, task_type, config)
VALUES (
    '1408252a-fd36-4fd3-b527-3b2f495d7b9c',
    'care_docs_check',
    '0 17 * * 0',
    'America/Chicago',
    'care_docs_check',
    '{"agent_slug": "med-check"}'
)
ON CONFLICT (org_id, name) DO NOTHING;
```

- [ ] Tests: all-current → sentinel (nothing published); one stale → message names the doc and reason; never_generated (both) → message present. Mirror tests/test_proactive_*.py fakes. Green, ruff, commit `feat(meds): weekly care-docs staleness check`.

---

### Task 6: Prompt v3 (migration 027 + synced copies)

**Files:** Create `supabase/migrations/027_med_check_prompt_v3.sql`; modify `evals/tasks/med_check.py::MED_CHECK_PROMPT`, docs fenced block, `tests/test_med_check_prompt_sync.py` (anchor 027).

- [ ] v3 = v2 byte-identical + these sections appended after the "Severity:" paragraph, before "Memory:" (SQL copy doubles apostrophes):

```
Care documents. Two living documents exist: an emergency one-pager for ER staff and first responders who likely know neither Rett syndrome nor congenital Long QT, and a caregiver handoff for grandparents, respite care, and the school nurse. When Jordan asks to set up, update, or generate either one: call get_care_profile and get_medication_profile first. If core sections are empty, run intake before composing.

Intake: one question at a time, in this order: critical_flags and diagnoses confirmation, seizure_plan, baselines, escalation, communication, routines, contacts. Save each answer with save_care_profile as it arrives so nothing is lost if the conversation drops. After each save, restate what you saved in one line so transcription errors get caught. If Jordan skips a section, record it as skipped and move on. Never invent or infer profile content. The generated documents mark missing sections as "not provided", never silently omitted: a stranger should know the plan is incomplete.

Emergency one-pager rules. It must print on one page: keep the body near 2,500 characters. Cut routine detail to fit, never safety content. Order is fixed: display name and DOB if provided, then CRITICAL first (the QT medication warning and other critical_flags at the very top), then diagnoses one line each, then seizure plan, then current medications and allergies from the medication profile live at generation time, then her baselines (things that look alarming but are normal for her), then communication basics, then contacts. Plain language. No abbreviations a first responder might not share. Write for someone with thirty seconds.

Handoff document rules. Audience: a competent adult who does not know her. Warmer register is fine, still concrete. Order: one-paragraph intro (who she is beyond diagnoses, drawing on the communication and comfort content), routines by time of day, communication and signals, seizure plan, escalation matrix (call Jordan, call the doctor, call 911, as observable triggers), medications only if a dose falls during typical care windows, otherwise say medications are handled by her parents, then contacts. Every instruction actionable: "offer choices by holding up two objects and watching her eyes" beats "she communicates with eye gaze".

Both documents end with the generation date and: maintained by her parents; not a medical record. The critical_flags QT warning is never cut, summarized, or moved below the top of either document. Compose the body, then write it with save_care_document. Your reply confirms what was written and lists any "not provided" sections.

Staleness: after any save_medication_profile or save_care_profile call, check check_care_docs_current. If a document went stale, say so in one line and offer to regenerate now. One line, one offer, no nagging.
```

- [ ] Sync test re-anchored on 027, 3/3 green; record v3 byte length. Commit `feat(meds): prompt v3 — care documents (migration 027)`.

---

### Task 7: Evals — care-doc cases

**Files:** evals fixtures/tasks/yaml/baseline + scorer reuse.

- Stubs for the 4 new tools (signatures minus ctx; save_care_document stub captures markdown_body into the phase-2 captured-notes mechanism so grading covers the doc body via ===NOTE===).
- Fixture: complete care profile (all 8 sections, contacts, the seeded QT flag verbatim) + the phase-1 med profile fixture.
- Cases (pinned LLMJudge + PhraseAssertionScorer):
  1. `emergency_complete` — "make her emergency sheet" → required_in-note (use required_phrases on the whole surface where acceptable): the QT warning string VERBATIM, "maintained by her parents"; forbidden_in_note: "not provided" (profile complete → must not appear); judge rubric: fixed order respected, meds match fixture, plain language, ~one-page.
  2. `emergency_missing_seizure_plan` — same with seizure_plan empty in fixture → required: "not provided"; judge: seizure section marked not provided AND the reply calls it out.
  3. `handoff_actionable` — "make the handoff doc for her grandparents" → forbidden_in_note: "diagnosis", "likely", "indicates"; required: escalation triggers present; judge: observable triggers, actionable instructions, intro paragraph.
  4. `stale_offer_once` — fixture flags emergency stale after a save → judge: exactly one regeneration offer, one line, no nagging.
- ONE smoke case then full 12-case run ONCE with --save-baseline (~12 runs + 12 judges ≈ $0.70-1.00 — record actuals). Investigate any infra drops.
- Commit `feat(evals): med_check care-document cases`.

---

### Task 8: Docs

- `docs/med-check-agent.md`: "Care documents (phase 3)" section — care profile schema, hash/staleness mechanism (per-doc field coverage), date-versioned titles, budget gate, weekly check → app briefing, intake rules, migrations 025/026/027 order, prompt v3. TODO hooks noted in code: PDF export; audience parameter for the handoff (family/school/respite) — documented as deliberately NOT built.
- `docs/architecture.md`: 33 tools, migrations 001-027, care_profiles/care_documents tables, care_docs_check in the scheduler executor list, med_check evals 12 cases.
- Commit `docs: med-check phase 3 — care documents`.

---

### Task 9: Deploy + prod verification

- [ ] 1 (Jordan): migration 025 in SQL Editor. Verify: care_profiles row exists with the seeded QT flag; care_documents empty.
- [ ] 2: merge, deploy-verify (SHA + /health).
- [ ] 3 (session): migration 026 via supabase-py (data; read back schedule row); migration 027 prompt v3 via supabase-py + byte-diff.
- [ ] 4: real round-trips: check_care_docs_current ("are her care docs up to date?") → both never_generated; intake conversation (Jordan answers what he wants; sections he skips get marked); "make her emergency sheet" → note row in Health/Documents/, care_documents row with hash, QT warning at top verbatim, budget respected; a med-profile edit → agent's one-line stale offer; weekly executor dry-run (invoke execute_care_docs_check directly via a python snippet against prod db — deterministic, no LLM) → correct staleness message.
- [ ] 5: update docs/med-check-ui-handoff.md (one line: care docs exist as vault artifacts; staleness nudges arrive in the briefing section).
- [ ] 6: ledger complete, workspace cleanup, memory.

## Self-Review

- Spec Task 1 ↔ plan Tasks 1-2 (all 9 spec sections map: display reuses timeline_display_name — confirmed existing; include_photo_path skipped with reason). Spec Task 2 (intake) ↔ prompt v3 intake block + save-as-you-go tools. Spec Task 3 ↔ save_care_document + hash + check_care_docs_current (generate_care_document trigger realized as compose-then-save_care_document; date-versioned titles per spec's fallback). Spec Task 4 ↔ prompt staleness rule + Task 5 executor/seed (app briefing = reconciled channel). Spec Task 5 ↔ prompt v3 (all 5 numbered requirements present incl. budget, fixed orders, closing line, QT-never-cut). Spec Task 6 ↔ Tasks 2/3/5 unit tests + Task 7 evals (all 4 cases + verbatim-QT grep). TODO hooks ↔ Task 8 docs + code comments.
- Judgment calls: hash coverage split per doc_type (spec's test mandates it); budget gate is deterministic in the tool (stronger than prompt-only); executor is LLM-free (mirrors weekly review's deterministic short-circuit philosophy); intake order copied from spec verbatim.
