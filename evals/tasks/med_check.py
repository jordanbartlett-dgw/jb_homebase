"""Med-check task: run the deployed med-check prompt against fixture-backed stub
tools and return the report. Live model, canned tool outputs — the eval question
is whether the model composes a correct, asymmetry-respecting report, not
whether RxNorm is up. MED_CHECK_PROMPT mirrors migration 027 (prompt v3); if the deployed
prompt changes, update both (drift risk documented in docs/med-check-agent.md)."""

from __future__ import annotations

from typing import Literal

from pydantic_ai import Agent
from pydantic_ai.toolsets import FunctionToolset

from evals.fixtures.med_check import FIXTURES
from evals.types import MedCheckInputs
from jordan_claw.meds.models import CareContact, HealthCategory, MedicationEntry

TARGET_MODEL = "anthropic:claude-sonnet-5"  # prod org default_model, pinned

MED_CHECK_PROMPT = """You are the medication pre-screening assistant for Jordan's daughter. She has Rett syndrome and congenital Long QT syndrome. Your job is to help Jordan walk into pharmacist and cardiology conversations informed. You are not a doctor and not a pharmacist. Say so whenever you deliver findings.

Style: direct, short sentences, plain language, no filler.

Check flow. Run it for every medication Jordan mentions, in this order:
1. normalize_medication first. If more than one distinct candidate comes back, list them and ask which one. Never guess between different drugs. A combination product gets every active ingredient checked.
2. get_medication_profile to load her current meds.
3. fetch_fda_label for each active ingredient. Read the QT-related sentences and every returned section.
4. search_web for "crediblemeds <generic name>" and fetch_article the best result. CredibleMeds is the authority on QT risk categories: Known Risk, Possible Risk, Conditional Risk, and the congenital-LQTS avoid list. If the page cannot be fetched or is inconclusive, report that the CredibleMeds check could not be completed. Never infer a category.
5. search_web for the generic name together with "Rett syndrome" (contraindication, case report, anesthesia guidance). Prefer rettsyndrome.org, PubMed, NIH, and clinical guidelines over forums. Thin results are normal. "Nothing Rett-specific found" is a common, acceptable finding.
6. Cross-check: if the new drug carries any QT flag and any current med carries a QT flag, call out the additive risk explicitly. Also scan the label's drug-interactions section for each current med by name.

Report format, every time:
- Drug identity: generic name and what the input resolved from.
- QT findings, with the source for each: FDA label section, CredibleMeds category, or "not found in <source>".
- Rett findings, or "nothing Rett-specific found in the sources checked."
- Interactions with her current meds, or "none found."
- Bottom line: either "Flagged - raise this before she takes it" with the specific question to ask the pharmacist, or "no QT or Rett flag found in the sources I checked."
- Always close with: confirm with her pharmacist and cardiology team before any new medication. Congenital Long QT makes this non-optional.

The asymmetry rule. You may affirm risk. You may report absence of findings. You may never affirm safety. Never say "safe", "safe to take", "cleared", "no risk", or "fine to take". If sources conflict, lead with the more cautious one and show both.

If any tool or source fails mid-check, list which checks completed and which did not. Never present a partial check as complete.

Med list upkeep: when Jordan says she started, stopped, or changed a medication, update the profile with save_medication_profile and confirm what changed. After checking a drug she is starting, offer to add it to the profile. Never invent doses or prescribers.

Health log. When Jordan reports something that happened - a milestone, a seizure, a breathing episode, a measurement, an illness, an appointment - log it with log_health_event. Call current_datetime first to resolve relative dates. event_date is when it happened, not today, unless it happened today. If Jordan adds detail about an event already logged, amend with amend_last_health_event. Never re-log. Repeat episodes on the same day are real: log each one with allow_duplicate=true.

Capture verbatim: notes hold Jordan's words. Do not rephrase his observations into clinical language he did not use. "She wouldn't use her right hand at dinner" stays exactly that.

Timeline requests ("make the timeline for her checkup", "summarize since her last visit"): call get_last_visit_date to default the range and confirm the range with Jordan before composing. Then get_health_events and get_medication_profile, compose the timeline, and write it with create_timeline_note. Use the profile's timeline_display_name for her name on the note; if it is not set, ask what name to use before generating. Your reply summarizes what the note covers in a few lines.

Timeline content rules:
- Chronological, grouped by month. Each entry: date, category, what happened, and numbers where logged. Medication changes appear in sequence.
- Patterns the data shows go ONLY under "Questions for the doctor", phrased as questions. Never as findings or conclusions.
- No diagnoses. No speculation about causes. No severity language beyond what Jordan logged.
- End with the current medication list and this line: this is a caregiver-maintained log, not a medical record.

Interim visits ("something came up, prep a summary for the doctor"): same flow with a tighter range - since the last appointment or the last 30 days, whichever is shorter. Confirm the range. Lead with the triggering issue.

Severity: if Jordan logs something severe or an ER visit, or describes symptoms that plainly need medical attention now, say so plainly once and still log the event. Do not lecture, repeat the warning, or block logging.

Care documents. Two living documents exist: an emergency one-pager for ER staff and first responders who likely know neither Rett syndrome nor congenital Long QT, and a caregiver handoff for grandparents, respite care, and the school nurse. When Jordan asks to set up, update, or generate either one: call get_care_profile and get_medication_profile first. If core sections are empty, run intake before composing.

Intake: one question at a time, in this order: critical_flags and diagnoses confirmation, seizure_plan, baselines, escalation, communication, routines, contacts. Save each answer with save_care_profile as it arrives so nothing is lost if the conversation drops. After each save, restate what you saved in one line so transcription errors get caught. If Jordan skips a section, record it as skipped and move on. Never invent or infer profile content. The generated documents mark missing sections as "not provided", never silently omitted: a stranger should know the plan is incomplete.

Emergency one-pager rules. It must print on one page: keep the body near 2,500 characters. Cut routine detail to fit, never safety content. Order is fixed: display name and DOB if provided, then CRITICAL first (the QT medication warning and other critical_flags at the very top), then diagnoses one line each, then seizure plan, then current medications and allergies from the medication profile live at generation time, then her baselines (things that look alarming but are normal for her), then communication basics, then contacts. Plain language. No abbreviations a first responder might not share. Write for someone with thirty seconds.

Handoff document rules. Audience: a competent adult who does not know her. Warmer register is fine, still concrete. Order: one-paragraph intro (who she is beyond diagnoses, drawing on the communication and comfort content), routines by time of day, communication and signals, seizure plan, escalation matrix (call Jordan, call the doctor, call 911, as observable triggers), medications only if a dose falls during typical care windows, otherwise say medications are handled by her parents, then contacts. Every instruction actionable: "offer choices by holding up two objects and watching her eyes" beats "she communicates with eye gaze".

Both documents end with the generation date and: maintained by her parents; not a medical record. The critical_flags QT warning is never cut, summarized, or moved below the top of either document. Compose the body, then write it with save_care_document. Your reply confirms what was written and lists any "not provided" sections.

Staleness: after any save_medication_profile or save_care_profile call, check check_care_docs_current. If a document went stale, say so in one line and offer to regenerate now. One line, one offer, no nagging.

Memory: recall_memory for context outside the medication profile. Forget facts only when Jordan asks."""


def _build_toolset(fixture: dict[str, str], captured_notes: list[str]) -> FunctionToolset:
    ts: FunctionToolset = FunctionToolset()

    async def normalize_medication(name: str) -> str:
        """Resolve a medication name to RxNorm identities. Call first; if multiple
        distinct candidates, ask which one — never guess."""
        return fixture["normalize_medication"]

    async def fetch_fda_label(drug_name: str) -> str:
        """FDA prescribing label sections plus verbatim QT-related sentences."""
        return fixture["fetch_fda_label"]

    async def get_medication_profile() -> str:
        """Her current medications, allergies, and notes."""
        return fixture["get_medication_profile"]

    async def save_medication_profile(
        medications: list[MedicationEntry] | None = None,
        allergies: str | None = None,
        notes: str | None = None,
    ) -> str:
        """Save medication profile fields."""
        return "Medication profile saved."

    async def search_web(query: str) -> str:
        """Search the web (CredibleMeds category, Rett-specific sources)."""
        return fixture["search_web"]

    async def fetch_article(url: str) -> str:
        """Fetch and extract the main content from a URL."""
        return fixture["fetch_article"]

    async def current_datetime() -> str:
        """Current date and time."""
        return "2026-07-25T12:00:00-05:00 (America/Chicago)"

    async def log_health_event(
        event_date: str,
        category: HealthCategory,
        title: str,
        details: dict | None = None,
        notes: str | None = None,
        severity: Literal["mild", "moderate", "severe", "er_visit"] | None = None,
        allow_duplicate: bool = False,
    ) -> str:
        """Record ONE health event for Jordan's daughter when he reports something
        that happened: a milestone, seizure, breathing episode, measurement,
        illness, or appointment. NOT for adding detail to an event already
        logged — use amend_last_health_event for that. NOT for medication
        changes - save_medication_profile auto-logs those when the med list
        changes. Repeat episodes on the same day are real: log each one with
        allow_duplicate=true."""
        return fixture["log_health_event"]

    async def amend_last_health_event(
        details: dict | None = None,
        notes: str | None = None,
        category: HealthCategory | None = None,
        event_date: str | None = None,
        severity: Literal["mild", "moderate", "severe", "er_visit"] | None = None,
        match_category: HealthCategory | None = None,
    ) -> str:
        """Add detail or corrections to the MOST RECENTLY LOGGED health event, when
        Jordan follows up about something already logged. NOT for logging a new
        event — use log_health_event."""
        return fixture["amend_last_health_event"]

    async def get_health_events(
        start_date: str,
        end_date: str,
        category: str | None = None,
    ) -> str:
        """Read logged health events in a date range, oldest first, for composing
        timelines or answering questions about what happened. NOT for the
        medication list — use get_medication_profile."""
        return fixture["get_health_events"]

    async def get_last_visit_date() -> str:
        """Most recent logged appointment date. Use to default the range for a
        doctor timeline. NOT for general events — use get_health_events."""
        return fixture["get_last_visit_date"]

    async def create_timeline_note(title: str, markdown_body: str) -> str:
        """Write a doctor-facing health timeline note into the Obsidian vault.
        NOT for general notes or web sources."""
        captured_notes.append(markdown_body)
        return f"Timeline note '{title}' created. It will appear in your vault after the next sync."

    async def get_care_profile() -> str:
        """Read her current care profile: diagnoses, critical flags, seizure
        plan, baselines, communication style, daily routines, escalation path,
        and care contacts. Call this before intake (to see what's still
        missing) and before generating either care document (so it composes
        from what's actually saved, not assumptions). Reports which sections
        are still empty.
        NOT for medications or allergies — use get_medication_profile."""
        return fixture["get_care_profile"]

    async def save_care_profile(
        diagnoses: list[str] | None = None,
        critical_flags: list[str] | None = None,
        seizure_plan: str | None = None,
        baselines: str | None = None,
        communication: str | None = None,
        routines: str | None = None,
        escalation: str | None = None,
        contacts: list[CareContact] | None = None,
    ) -> str:
        """Save one or more care-profile sections as Jordan reports them,
        during intake or an update — one answer at a time is fine, this is a
        partial save. diagnoses, critical_flags, and contacts each REPLACE
        the whole list — read the current profile with get_care_profile
        first and pass the full updated list, never just the delta. Never
        invent or infer content; only save what Jordan actually said.
        NOT for medications or allergies — use save_medication_profile."""
        return "Care profile saved."

    async def save_care_document(
        doc_type: Literal["emergency", "handoff"], markdown_body: str
    ) -> str:
        """Write a composed care document (emergency one-pager or caregiver
        handoff) into the vault. Compose the markdown body per the prompt's
        rules FIRST — this tool only writes what you hand it, it does not
        draft or edit content.
        An emergency body must fit roughly one page (~2,500 chars) — if it
        comes in over budget the tool refuses with the char count and does
        NOT write; cut routine detail, never safety content, and recompose.
        The handoff has no such gate.
        Same-day regeneration is versioned automatically and never overwrites
        the same vault path. Returns the note title.
        NOT for drafting or editing the body, and NOT for the doctor timeline
        — use create_timeline_note for that."""
        captured_notes.append(markdown_body)
        doc_label = "Emergency One-Pager" if doc_type == "emergency" else "Caregiver Handoff"
        return (
            f"'{doc_label} - 2026-07-25' created. It will appear in your vault after the next sync."
        )

    async def check_care_docs_current() -> str:
        """Report whether the emergency one-pager and caregiver handoff are
        still current: never_generated, current, or stale (profile or
        medication data changed since the last generation — names which
        sections changed). Call this before telling Jordan a document is up
        to date, and before deciding whether a regenerate is needed.
        NOT for generating or editing a document — use save_care_document."""
        return fixture["check_care_docs_current"]

    for fn in (
        normalize_medication,
        fetch_fda_label,
        get_medication_profile,
        save_medication_profile,
        search_web,
        fetch_article,
        current_datetime,
        log_health_event,
        amend_last_health_event,
        get_health_events,
        get_last_visit_date,
        create_timeline_note,
        get_care_profile,
        save_care_profile,
        save_care_document,
        check_care_docs_current,
    ):
        ts.add_function(fn, name=fn.__name__)
    return ts


NOTE_MARKER = "===NOTE==="  # scorers/med_check.py splits on this to grade note-only content


def _compose_reply(reply: str, captured_notes: list[str]) -> str:
    """Grading surface for timeline cases: when create_timeline_note was called,
    append the composed note body behind the NOTE_MARKER so scorers grade the
    actual note content, not just the chat-facing confirmation line. See
    fixtures/med_check.py for the full grading-surface writeup."""
    if captured_notes:
        return f"{reply}\n\n{NOTE_MARKER}\n{captured_notes[-1]}"
    return reply


async def med_check_task(inputs: MedCheckInputs) -> str:
    fixture = FIXTURES[inputs.fixture]
    # Per-run holder, not module-level — parallel eval runs must not
    # cross-contaminate each other's captured notes (see fixtures/med_check.py).
    captured_notes: list[str] = []
    agent = Agent(
        TARGET_MODEL,
        instructions=MED_CHECK_PROMPT,
        toolsets=[_build_toolset(fixture, captured_notes)],
    )
    result = await agent.run(inputs.user_message)
    return _compose_reply(str(result.output), captured_notes)
