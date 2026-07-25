from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Literal

import httpx
import structlog
import yaml
from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.health_log import (
    get_events_for_date,
    get_health_events_range,
    get_last_appointment_date,
    get_latest_health_event,
    insert_health_event,
    update_health_event,
)
from jordan_claw.db.meds import get_medication_profile, upsert_medication_profile
from jordan_claw.db.obsidian import insert_chunks, insert_note
from jordan_claw.meds.models import HealthCategory, MedicationEntry
from jordan_claw.obsidian.embeddings import chunk_text, generate_embeddings
from jordan_claw.tools.calendar import CENTRAL_TZ

log = structlog.get_logger()

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"
HTTP_TIMEOUT_S = 10.0
MAX_CANDIDATES = 4

# Cached so the underlying httpx connection pool is reused across calls
# (same pattern as web_search/embeddings client caches).
_http_client: httpx.AsyncClient | None = None


def get_meds_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT_S)
    return _http_client


async def _get_json(url: str, params: dict | None = None) -> tuple[int, dict | None]:
    """GET a JSON endpoint. Returns (status_code, body). status 0 = network failure.

    Callers must distinguish 404/empty (a real "not found" answer) from 0/5xx
    (the call failed) — the agent reports these differently.
    """
    try:
        resp = await get_meds_http_client().get(url, params=params)
    except httpx.HTTPError as exc:
        log.warning("meds_http_error", url=url, error=str(exc))
        return 0, None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return resp.status_code, body


_BRAND_TTYS = {"BN", "SBD", "SBDC", "BPCK"}
_GENERIC_TTYS = {"IN", "MIN", "PIN", "SCD", "SCDC", "GPCK"}


async def _candidate_summary(rxcui: str) -> str | None:
    """One formatted line for an rxcui: canonical name, brand/generic, ingredients."""
    status, props = await _get_json(f"{RXNAV_BASE}/rxcui/{rxcui}/properties.json")
    if status != 200 or not props or "properties" not in props:
        return None
    name = props["properties"].get("name", "?")
    tty = props["properties"].get("tty", "")
    kind = (
        "brand" if tty in _BRAND_TTYS else "generic" if tty in _GENERIC_TTYS else tty or "unknown"
    )

    status, related = await _get_json(f"{RXNAV_BASE}/rxcui/{rxcui}/related.json", {"tty": "IN"})
    if status != 200 or related is None:
        ing = (
            "(ingredient lookup FAILED — could not verify ingredients, "
            "report the check as incomplete)"
        )
    else:
        ingredients: list[str] = []
        for group in (related.get("relatedGroup") or {}).get("conceptGroup") or []:
            for concept in group.get("conceptProperties") or []:
                if concept.get("name") and concept["name"] not in ingredients:
                    ingredients.append(concept["name"])
        ing = ", ".join(ingredients) if ingredients else "(ingredient lookup returned nothing)"
    return f"- rxcui {rxcui}: {name} ({kind}) — active ingredient(s): {ing}"


async def normalize_medication(ctx: RunContext[AgentDeps], name: str) -> str:
    """Resolve a medication name (including misspellings and brand names) to RxNorm
    identities with rxcui, canonical name, brand/generic, and every active ingredient.
    ALWAYS call this first for any medication mentioned, before any other check.
    If more than one distinct drug comes back, present the candidates and ask Jordan
    which one — never guess between different drugs. A single strong match may proceed.
    NOT for safety information — use fetch_fda_label and web search for that."""
    status, data = await _get_json(
        f"{RXNAV_BASE}/approximateTerm.json", {"term": name, "maxEntries": MAX_CANDIDATES}
    )
    if status != 200 or data is None:
        return (
            f"RxNorm lookup failed for '{name}' (network or API error). "
            "Report that drug identity could not be verified; do not guess."
        )

    candidates = (data.get("approximateGroup") or {}).get("candidate") or []
    seen: list[str] = []
    for cand in candidates:
        rxcui = cand.get("rxcui")
        if rxcui and rxcui not in seen:
            seen.append(rxcui)

    if not seen:
        return f"No RxNorm match for '{name}'. Ask Jordan to check the spelling or the packaging."

    lines: list[str] = []
    for rxcui in seen[:MAX_CANDIDATES]:
        summary = await _candidate_summary(rxcui)
        if summary:
            lines.append(summary)

    if not lines:
        return (
            f"RxNorm matched '{name}' but detail lookups failed (network or API error). "
            "Report that drug identity could not be verified; do not guess."
        )

    header = f"RxNorm candidates for '{name}':"
    if len(lines) > 1:
        header += " MULTIPLE distinct candidates — ask Jordan which one before checking."
    return header + "\n" + "\n".join(lines)


OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
SECTION_CHAR_BUDGET = 1500
LABEL_SECTIONS = (
    "boxed_warning",
    "contraindications",
    "warnings",
    "warnings_and_cautions",
    "precautions",
    "general_precautions",
    "drug_interactions",
    "adverse_reactions",
)
QT_PATTERN = re.compile(r"\bQTc?\b|torsade|arrhythmi|proarrhythmic|sudden death", re.IGNORECASE)


def _qt_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if QT_PATTERN.search(s)]


def _clip(text: str, budget: int = SECTION_CHAR_BUDGET) -> str:
    return text if len(text) <= budget else text[:budget] + " [truncated]"


async def fetch_fda_label(ctx: RunContext[AgentDeps], drug_name: str) -> str:
    """Fetch the FDA prescribing label for a drug from openFDA and return the
    safety-relevant sections (boxed warning, contraindications, warnings,
    interactions, adverse reactions) plus every QT/torsades/arrhythmia sentence
    extracted verbatim. Call with the GENERIC name from normalize_medication;
    it falls back to brand-name search automatically.
    NOT for drug identity (use normalize_medication) and NOT a CredibleMeds
    category (use web search for that)."""
    result: dict | None = None
    failed = False
    for field in ("openfda.generic_name", "openfda.brand_name"):
        status, data = await _get_json(
            OPENFDA_LABEL_URL, {"search": f'{field}:"{drug_name}"', "limit": 1}
        )
        if status == 200 and data and data.get("results"):
            result = data["results"][0]
            break
        if status in (0,) or status >= 500:
            failed = True
    if result is None:
        if failed:
            return (
                f"openFDA query failed for '{drug_name}' (network or API error). "
                "The FDA-label check did NOT complete — report it as incomplete."
            )
        return (
            f"No FDA label found for '{drug_name}' (searched generic and brand name). "
            "This is a definitive no-result, not an error."
        )

    parts: list[str] = []
    qt_hits: list[str] = []
    for section in LABEL_SECTIONS:
        values = result.get(section)
        if not values:
            continue
        text = "\n".join(values) if isinstance(values, list) else str(values)
        qt_hits.extend(_qt_sentences(text))
        parts.append(f"## {section}\n{_clip(text)}")

    pharm = result.get("clinical_pharmacology")
    if pharm:
        text = "\n".join(pharm) if isinstance(pharm, list) else str(pharm)
        hits = _qt_sentences(text)
        if hits:  # only include this section when it mentions QT
            qt_hits.extend(hits)
            parts.append(f"## clinical_pharmacology\n{_clip(text)}")

    deduped: list[str] = []
    for hit in qt_hits:
        if hit not in deduped:
            deduped.append(hit)
    if deduped:
        qt_block = "## QT-RELATED SENTENCES (verbatim, never truncated)\n" + "\n".join(
            f"- {h}" for h in deduped
        )
        parts.insert(0, qt_block)
    else:
        parts.insert(0, "## QT-RELATED SENTENCES\nNone found in the label sections returned.")

    if len(parts) == 1:
        parts.append("(No safety sections present in this label.)")
    return f"FDA label for '{drug_name}':\n\n" + "\n\n".join(parts)


async def get_medication_profile_tool(ctx: RunContext[AgentDeps]) -> str:
    """Read her current medication profile: medications (name, rxcui, dose,
    prescriber), known allergies, and notes (cardiology contact, baseline QTc).
    Call this at the start of every medication check so new drugs are assessed
    against what she already takes. Reports which fields are still empty.
    NOT for drug safety data — use fetch_fda_label and web search for that."""
    profile = await get_medication_profile(ctx.deps.supabase_client, ctx.deps.org_id)
    if profile is None:
        return (
            "No medication profile exists yet. Fields to collect: current medications "
            "(name, dose, prescriber), known allergies, notes (cardiology contact, baseline QTc)."
        )
    missing = profile.missing_fields()
    status = (
        "Profile is complete."
        if not missing
        else f"Profile incomplete. Empty fields: {', '.join(missing)}."
    )
    return f"{status}\n\n{profile.model_dump_json(exclude={'org_id'}, indent=2)}"


async def save_medication_profile(
    ctx: RunContext[AgentDeps],
    medications: list[MedicationEntry] | None = None,
    allergies: str | None = None,
    notes: str | None = None,
    timeline_display_name: str | None = None,
) -> str:
    """Save medication profile fields when Jordan reports a change (started,
    stopped, or changed a med; new allergy; updated contacts). Partial saves are
    fine: only pass the fields being changed. medications REPLACES the whole
    list — read the profile first and pass the full updated list.
    timeline_display_name controls the name shown on shared documents; set it
    when Jordan says what name to use.
    NOT for logging symptoms or events, and never invent doses or prescribers."""
    med_change_details: dict = {}
    if medications is not None:
        existing = await get_medication_profile(ctx.deps.supabase_client, ctx.deps.org_id)
        old_by_name = {m.name: m for m in (existing.medications if existing is not None else [])}
        new_by_name = {m.name: m for m in medications}

        added = [name for name in new_by_name if name not in old_by_name]
        removed = [name for name in old_by_name if name not in new_by_name]
        changed = [
            {"name": name, "dose_from": old_by_name[name].dose, "dose_to": new_by_name[name].dose}
            for name in new_by_name
            if name in old_by_name and old_by_name[name].dose != new_by_name[name].dose
        ]
        if added:
            med_change_details["added"] = added
        if removed:
            med_change_details["removed"] = removed
        if changed:
            med_change_details["changed"] = changed

    await upsert_medication_profile(
        ctx.deps.supabase_client,
        ctx.deps.org_id,
        medications=[m.model_dump() for m in medications] if medications is not None else None,
        allergies=allergies,
        notes=notes,
        timeline_display_name=timeline_display_name,
    )

    if not med_change_details:
        return "Medication profile saved."

    try:
        await insert_health_event(
            ctx.deps.supabase_client,
            ctx.deps.org_id,
            event_date=datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d"),
            category="medication_change",
            title="Medication change",
            details=med_change_details,
        )
    except Exception:
        log.warning("med_change_autolog_failed", details=med_change_details, exc_info=True)
        return (
            "Medication profile saved. Could not auto-log the medication_change "
            "event - tell Jordan the timeline is missing this change."
        )

    summary_parts = []
    if "added" in med_change_details:
        summary_parts.append(f"added {', '.join(med_change_details['added'])}")
    if "removed" in med_change_details:
        summary_parts.append(f"removed {', '.join(med_change_details['removed'])}")
    if "changed" in med_change_details:
        summary_parts.append(
            "; ".join(
                f"changed {c['name']} from {c['dose_from']} to {c['dose_to']}"
                for c in med_change_details["changed"]
            )
        )
    return (
        "Medication profile saved. Logged a medication_change event: "
        + "; ".join(summary_parts)
        + "."
    )


async def log_health_event(
    ctx: RunContext[AgentDeps],
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
    illness, appointment, or medication change. event_date is when it HAPPENED
    (resolve relative dates with current_datetime first), which is often not
    today. notes hold Jordan's exact words.
    NOT for adding detail to an event already logged — use
    amend_last_health_event for that. A same-day event of the same category is
    refused unless allow_duplicate=true; repeat episodes on the same day
    (a second seizure) are real and expected — pass allow_duplicate=true and
    log each one."""
    if not allow_duplicate:
        same_day = await get_events_for_date(ctx.deps.supabase_client, ctx.deps.org_id, event_date)
        clashes = [event for event in same_day if event.category == category]
        if clashes:
            existing = clashes[0]
            detail = ", ".join(f"{k}={v}" for k, v in existing.details.items())
            summary = " — ".join(p for p in (detail, existing.notes) if p)
            existing_desc = f'"{existing.title}"' + (f" — {summary}" if summary else "")
            return (
                f"Not logged: a {category} event for {event_date} already exists "
                f"({existing_desc}). If Jordan is adding detail about that same event, call "
                "amend_last_health_event instead. Repeat episodes on the same day are real "
                "and expected — if this is a genuinely separate occurrence, call "
                "log_health_event again with allow_duplicate=true."
            )

    await insert_health_event(
        ctx.deps.supabase_client,
        ctx.deps.org_id,
        event_date=event_date,
        category=category,
        title=title,
        details=details,
        notes=notes,
        severity=severity,
    )
    return f"Logged {category} for {event_date}: {title}."


async def amend_last_health_event(
    ctx: RunContext[AgentDeps],
    details: dict | None = None,
    notes: str | None = None,
    category: HealthCategory | None = None,
    event_date: str | None = None,
    severity: Literal["mild", "moderate", "severe", "er_visit"] | None = None,
) -> str:
    """Add detail or corrections to the MOST RECENTLY LOGGED health event, when
    Jordan follows up about something already logged. details keys merge into
    existing ones; notes append on a new line; category/event_date/severity
    replace if given. NOT for logging a new event — use log_health_event."""
    latest = await get_latest_health_event(ctx.deps.supabase_client, ctx.deps.org_id)
    if latest is None:
        return "No health event logged yet. Use log_health_event to record one."

    merged_details = {**latest.details, **(details or {})} if details else None
    merged_notes = None
    if notes:
        merged_notes = f"{latest.notes}\n{notes}" if latest.notes else notes

    await update_health_event(
        ctx.deps.supabase_client,
        ctx.deps.org_id,
        latest.id,
        details=merged_details,
        notes=merged_notes,
        category=category,
        event_date=event_date,
        severity=severity,
    )
    return f"Updated the {category or latest.category} event for {event_date or latest.event_date}."


async def get_health_events(
    ctx: RunContext[AgentDeps],
    start_date: str,
    end_date: str,
    category: str | None = None,
) -> str:
    """Read logged health events in a date range, oldest first, for composing
    timelines or answering questions about what happened. Includes a
    '(logged N days later)' marker when an event was recorded more than a day
    after it happened — the recall gap itself is useful for the timeline.
    NOT for the medication list — use get_medication_profile."""
    events = await get_health_events_range(
        ctx.deps.supabase_client, ctx.deps.org_id, start_date, end_date, category=category
    )
    if not events:
        return "No health events logged in that range."

    lines = []
    for event in events:
        detail = ", ".join(f"{k}={v}" for k, v in event.details.items())
        parts = [f"- [{event.event_date}] {event.category}: {event.title}"]
        if detail:
            parts.append(f"({detail})")
        if event.notes:
            parts.append(f"— {event.notes}")
        line = " ".join(parts)

        event_date_obj = datetime.strptime(event.event_date, "%Y-%m-%d").date()
        logged_date_obj = datetime.fromisoformat(event.logged_at).date()
        gap_days = (logged_date_obj - event_date_obj).days
        if gap_days > 1:
            line += f" (logged {gap_days} days later)"

        lines.append(line)
    return "\n".join(lines)


async def get_last_visit_date(ctx: RunContext[AgentDeps]) -> str:
    """Most recent logged appointment date. Use to default the range for a
    doctor timeline ('since her last visit'). Returns a clear no-appointments
    message when none is logged — then ask Jordan for the range instead of
    guessing. NOT for general events — use get_health_events."""
    last_date = await get_last_appointment_date(ctx.deps.supabase_client, ctx.deps.org_id)
    if last_date is None:
        return "No appointments logged yet. Ask Jordan for the range instead of guessing."
    return f"Most recent logged appointment: {last_date}."


async def create_timeline_note(
    ctx: RunContext[AgentDeps],
    title: str,
    markdown_body: str,
) -> str:
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
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    frontmatter = {
        "type": "health-timeline",
        "title": title,
        "generated": today,
        "tags": ["health", "timeline"],
        "status": "generated",
    }

    vault_path = f"Health/Timelines/{title}.md"

    # Build the full file content for hashing (frontmatter + body)
    full_file = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n\n{markdown_body}"
    content_hash = hashlib.sha256(full_file.encode()).hexdigest()

    note_row = await insert_note(
        ctx.deps.supabase_client,
        org_id=ctx.deps.org_id,
        vault_path=vault_path,
        title=title,
        note_type="health_timeline",
        content=markdown_body,
        frontmatter=frontmatter,
        tags=["health", "timeline"],
        wiki_links=[],
        content_hash=content_hash,
        source_origin="claw",
        sync_status="pending_export",
    )

    # Generate chunks and embeddings
    chunks = chunk_text(markdown_body)
    embeddings = await generate_embeddings(
        [c["content"] for c in chunks],
        api_key=ctx.deps.openai_api_key,
    )

    note_id = note_row.get("id", "")
    chunk_rows = [
        {
            "note_id": note_id,
            "chunk_index": c["chunk_index"],
            "content": c["content"],
            "embedding": embeddings[i],
            "token_count": c["token_count"],
        }
        for i, c in enumerate(chunks)
    ]
    await insert_chunks(ctx.deps.supabase_client, chunk_rows)

    # TODO(phase-2-followup): PDF export would hook here — compose once, render twice.
    return f"Timeline note '{title}' created. It will appear in your vault after the next sync."
