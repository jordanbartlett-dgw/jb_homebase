from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from jordan_claw.meds.models import CareContact, CareProfile, MedicationEntry, MedicationProfile
from jordan_claw.tools import meds

ORG_ID = "org-1"


def make_deps():
    from jordan_claw.agents.deps import AgentDeps

    return AgentDeps(
        org_id=ORG_ID,
        tavily_api_key="tv",
        fastmail_username="u",
        fastmail_app_password="p",
        openai_api_key="oa",
    )


class FakeCtx:
    def __init__(self):
        self.deps = make_deps()


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 7, 25, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# _care_source_hash / _section_hash
# ---------------------------------------------------------------------------


def test_section_hash_is_key_order_independent():
    a = meds._section_hash({"x": 1, "y": 2})
    b = meds._section_hash({"y": 2, "x": 1})
    assert a == b


def test_care_source_hash_deterministic_same_inputs():
    care = CareProfile(org_id=ORG_ID, diagnoses=["Long QT syndrome"])
    meds_profile = MedicationProfile(org_id=ORG_ID, timeline_display_name="Ellie")
    h1 = meds._care_source_hash("handoff", care, meds_profile)
    h2 = meds._care_source_hash("handoff", care, meds_profile)
    assert h1 == h2
    bundle = json.loads(h1)
    assert "total" in bundle and "sections" in bundle


def test_med_edit_flips_emergency_but_not_handoff():
    care = CareProfile(org_id=ORG_ID, diagnoses=["Long QT syndrome"])
    meds_a = MedicationProfile(
        org_id=ORG_ID,
        timeline_display_name="Ellie",
        medications=[MedicationEntry(name="ondansetron", dose="4mg")],
    )
    meds_b = MedicationProfile(
        org_id=ORG_ID,
        timeline_display_name="Ellie",
        medications=[MedicationEntry(name="ondansetron", dose="8mg")],
    )

    emergency_a = json.loads(meds._care_source_hash("emergency", care, meds_a))
    emergency_b = json.loads(meds._care_source_hash("emergency", care, meds_b))
    assert emergency_a["total"] != emergency_b["total"]
    assert emergency_a["sections"]["medications"] != emergency_b["sections"]["medications"]

    handoff_a = json.loads(meds._care_source_hash("handoff", care, meds_a))
    handoff_b = json.loads(meds._care_source_hash("handoff", care, meds_b))
    assert handoff_a["total"] == handoff_b["total"]
    assert handoff_a["sections"] == handoff_b["sections"]


def test_care_edit_flips_both_doc_types():
    meds_profile = MedicationProfile(org_id=ORG_ID, timeline_display_name="Ellie")
    care_a = CareProfile(org_id=ORG_ID, seizure_plan="call 911 if seizure > 5 min")
    care_b = CareProfile(org_id=ORG_ID, seizure_plan="call 911 if seizure > 3 min")

    for doc_type in ("emergency", "handoff"):
        bundle_a = json.loads(meds._care_source_hash(doc_type, care_a, meds_profile))
        bundle_b = json.loads(meds._care_source_hash(doc_type, care_b, meds_profile))
        assert bundle_a["total"] != bundle_b["total"], doc_type
        assert bundle_a["sections"]["seizure_plan"] != bundle_b["sections"]["seizure_plan"]


# ---------------------------------------------------------------------------
# check_care_docs_current
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_care_docs_never_generated(monkeypatch):
    monkeypatch.setattr(
        meds, "get_care_profile", lambda *a, **kw: _async_return(CareProfile(org_id=ORG_ID))
    )
    monkeypatch.setattr(
        meds,
        "get_medication_profile",
        lambda *a, **kw: _async_return(MedicationProfile(org_id=ORG_ID)),
    )
    monkeypatch.setattr(meds, "get_care_document", lambda *a, **kw: _async_return(None))

    out = await meds.check_care_docs_current(FakeCtx())
    assert "emergency: never_generated" in out
    assert "handoff: never_generated" in out


@pytest.mark.asyncio
async def test_check_care_docs_names_changed_section(monkeypatch):
    """Stored hash was computed from an old care profile with a different
    seizure_plan; current profile changed only that section. The stale report
    for both doc types must name seizure_plan and nothing else that didn't
    change."""
    old_care = CareProfile(
        org_id=ORG_ID,
        diagnoses=["Long QT syndrome"],
        seizure_plan="call 911 if seizure > 5 min",
    )
    new_care = CareProfile(
        org_id=ORG_ID,
        diagnoses=["Long QT syndrome"],
        seizure_plan="call 911 if seizure > 3 min",
    )
    meds_profile = MedicationProfile(org_id=ORG_ID, timeline_display_name="Ellie")

    stored_hash = meds._care_source_hash("emergency", old_care, meds_profile)
    stored_handoff_hash = meds._care_source_hash("handoff", old_care, meds_profile)

    monkeypatch.setattr(meds, "get_care_profile", lambda *a, **kw: _async_return(new_care))
    monkeypatch.setattr(
        meds, "get_medication_profile", lambda *a, **kw: _async_return(meds_profile)
    )

    async def fake_get_care_document(client, org_id, doc_type):
        if doc_type == "emergency":
            return {"source_hash": stored_hash, "generated_at": "2026-07-01T00:00:00+00:00"}
        return {"source_hash": stored_handoff_hash, "generated_at": "2026-07-01T00:00:00+00:00"}

    monkeypatch.setattr(meds, "get_care_document", fake_get_care_document)

    out = await meds.check_care_docs_current(FakeCtx())
    for line in out.splitlines():
        if line.startswith("emergency") or line.startswith("handoff"):
            assert "stale" in line
            assert "seizure_plan" in line
            assert "diagnoses" not in line


@pytest.mark.asyncio
async def test_check_care_docs_unreadable_stored_hash_is_explicit(monkeypatch):
    """A garbage/legacy source_hash (not our {"total", "sections"} bundle)
    must not be silently treated as if every section changed — report it as
    unreadable instead of overclaiming specifics."""
    care = CareProfile(org_id=ORG_ID, diagnoses=["Long QT syndrome"])
    meds_profile = MedicationProfile(org_id=ORG_ID, timeline_display_name="Ellie")

    monkeypatch.setattr(meds, "get_care_profile", lambda *a, **kw: _async_return(care))
    monkeypatch.setattr(
        meds, "get_medication_profile", lambda *a, **kw: _async_return(meds_profile)
    )

    async def fake_get_care_document(client, org_id, doc_type):
        return {
            "source_hash": "not-json-and-not-a-bundle",
            "generated_at": "2026-07-01T00:00:00+00:00",
        }

    monkeypatch.setattr(meds, "get_care_document", fake_get_care_document)

    out = await meds.check_care_docs_current(FakeCtx())
    for line in out.splitlines():
        assert "stored hash unreadable - regenerate to reset" in line
        assert "changed:" not in line


async def _async_return(value):
    return value


# ---------------------------------------------------------------------------
# get_care_profile_tool / save_care_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_care_profile_tool_reports_empty_when_none(monkeypatch):
    monkeypatch.setattr(meds, "get_care_profile", lambda *a, **kw: _async_return(None))
    out = await meds.get_care_profile_tool(FakeCtx())
    assert "No care profile exists yet" in out


@pytest.mark.asyncio
async def test_get_care_profile_tool_reports_empty_sections(monkeypatch):
    profile = CareProfile(org_id=ORG_ID, diagnoses=["Long QT syndrome"])
    monkeypatch.setattr(meds, "get_care_profile", lambda *a, **kw: _async_return(profile))
    out = await meds.get_care_profile_tool(FakeCtx())
    assert "Empty sections:" in out
    assert "baselines" in out


@pytest.mark.asyncio
async def test_save_care_profile_forwards_partial_fields(monkeypatch):
    captured: dict = {}

    async def fake_upsert(client, org_id, **fields):
        captured.update(fields)

    monkeypatch.setattr(meds, "upsert_care_profile", fake_upsert)

    out = await meds.save_care_profile(FakeCtx(), seizure_plan="call 911 if seizure > 5 min")
    assert out == "Care profile saved."
    assert captured["seizure_plan"] == "call 911 if seizure > 5 min"
    assert captured["diagnoses"] is None


@pytest.mark.asyncio
async def test_save_care_profile_dumps_contacts_before_db_boundary(monkeypatch):
    """Carried finding from Task 2 review: contacts must be model_dump()'d
    before crossing into the db layer, not passed as CareContact instances."""
    captured: dict = {}

    async def fake_upsert(client, org_id, **fields):
        captured.update(fields)

    monkeypatch.setattr(meds, "upsert_care_profile", fake_upsert)

    contacts = [CareContact(role="mom", name="Jane", phone="555-1234")]
    await meds.save_care_profile(FakeCtx(), contacts=contacts)

    assert captured["contacts"] == [{"role": "mom", "name": "Jane", "phone": "555-1234"}]
    assert all(isinstance(c, dict) for c in captured["contacts"])


# ---------------------------------------------------------------------------
# save_care_profile: critical_flags wipe guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_care_profile_refuses_wipe_when_flags_exist(monkeypatch):
    """critical_flags=[] against a profile that already has flags on file
    must refuse and never reach upsert_care_profile. Zero-write proof via
    the AssertionError-raising stand-in."""
    existing = CareProfile(org_id=ORG_ID, critical_flags=[DEFAULT_CRITICAL_FLAG])
    monkeypatch.setattr(meds, "get_care_profile", lambda *a, **kw: _async_return(existing))

    def _fail_upsert(*a, **kw):
        raise AssertionError("must not upsert when the wipe guard refuses")

    monkeypatch.setattr(meds, "upsert_care_profile", _fail_upsert)

    out = await meds.save_care_profile(FakeCtx(), critical_flags=[])

    assert out == (
        "Not saved: that would remove every critical flag. To remove a specific "
        "flag, pass the reduced list; to clear them all, Jordan must confirm "
        "explicitly - tell him what you are removing and why."
    )


@pytest.mark.asyncio
async def test_save_care_profile_allows_reduced_flag_list(monkeypatch):
    """A non-empty replacement list (dropping one flag, keeping another) is
    never a wipe, it must save normally."""
    existing = CareProfile(org_id=ORG_ID, critical_flags=[DEFAULT_CRITICAL_FLAG, "second flag"])
    monkeypatch.setattr(meds, "get_care_profile", lambda *a, **kw: _async_return(existing))

    captured: dict = {}

    async def fake_upsert(client, org_id, **fields):
        captured.update(fields)

    monkeypatch.setattr(meds, "upsert_care_profile", fake_upsert)

    out = await meds.save_care_profile(FakeCtx(), critical_flags=[DEFAULT_CRITICAL_FLAG])

    assert out == "Care profile saved."
    assert captured["critical_flags"] == [DEFAULT_CRITICAL_FLAG]


@pytest.mark.asyncio
async def test_save_care_profile_allows_empty_when_no_existing_flags(monkeypatch):
    """critical_flags=[] is not a wipe when there was nothing to wipe: no
    existing profile, and a profile with an already-empty critical_flags,
    must both save through."""
    captured_calls: list[dict] = []

    async def fake_upsert(client, org_id, **fields):
        captured_calls.append(fields)

    monkeypatch.setattr(meds, "upsert_care_profile", fake_upsert)

    monkeypatch.setattr(meds, "get_care_profile", lambda *a, **kw: _async_return(None))
    out = await meds.save_care_profile(FakeCtx(), critical_flags=[])
    assert out == "Care profile saved."

    existing_empty = CareProfile(org_id=ORG_ID, critical_flags=[])
    monkeypatch.setattr(meds, "get_care_profile", lambda *a, **kw: _async_return(existing_empty))
    out = await meds.save_care_profile(FakeCtx(), critical_flags=[])
    assert out == "Care profile saved."

    assert len(captured_calls) == 2
    assert all(call["critical_flags"] == [] for call in captured_calls)


# ---------------------------------------------------------------------------
# save_care_document
# ---------------------------------------------------------------------------


DEFAULT_CRITICAL_FLAG = (
    "Long QT syndrome - avoid QT-prolonging medications, confirm with cardiology."
)


def _patch_successful_write(monkeypatch, care=None, meds_profile=None, existing_paths=()):
    """Wire every dependency save_care_document needs for a real write, and
    return the captured insert_note/upsert_care_document call args.
    existing_paths simulates what get_vault_paths_with_prefix would find
    already in obsidian_notes — pass the exact same-day path to exercise the
    version-suffix collision handling.
    The default care profile carries DEFAULT_CRITICAL_FLAG so emergency-doc
    tests clear the critical-flags gate; callers exercising that gate itself
    pass their own care profile and body."""
    captured: dict = {}

    meds_profile = meds_profile or MedicationProfile(org_id=ORG_ID, timeline_display_name="Ellie")
    care = (
        care
        if care is not None
        else CareProfile(
            org_id=ORG_ID,
            diagnoses=["Long QT syndrome"],
            critical_flags=[DEFAULT_CRITICAL_FLAG],
        )
    )

    monkeypatch.setattr(
        meds, "get_medication_profile", lambda *a, **kw: _async_return(meds_profile)
    )
    monkeypatch.setattr(meds, "get_care_profile", lambda *a, **kw: _async_return(care))
    monkeypatch.setattr(
        meds, "get_vault_paths_with_prefix", lambda *a, **kw: _async_return(list(existing_paths))
    )

    async def fake_insert_note(client, **kwargs):
        captured["insert_note"] = kwargs
        return {"id": "note-1"}

    async def fake_generate_embeddings(texts, api_key):
        return [[0.0, 0.0]] * len(texts)

    async def fake_insert_chunks(client, chunks):
        captured["chunks"] = chunks

    async def fake_upsert_care_document(client, org_id, *, doc_type, source_hash, note_title):
        captured["upsert_care_document"] = {
            "org_id": org_id,
            "doc_type": doc_type,
            "source_hash": source_hash,
            "note_title": note_title,
        }

    monkeypatch.setattr(meds, "insert_note", fake_insert_note)
    monkeypatch.setattr(meds, "generate_embeddings", fake_generate_embeddings)
    monkeypatch.setattr(meds, "insert_chunks", fake_insert_chunks)
    monkeypatch.setattr(meds, "upsert_care_document", fake_upsert_care_document)
    monkeypatch.setattr(meds, "datetime", _FixedDatetime)

    return captured


@pytest.mark.asyncio
async def test_save_care_document_refuses_when_display_name_unset(monkeypatch):
    monkeypatch.setattr(
        meds,
        "get_medication_profile",
        lambda *a, **kw: _async_return(MedicationProfile(org_id=ORG_ID)),
    )

    def _fail_insert_note(*a, **kw):
        raise AssertionError("must not write when display name is unset")

    monkeypatch.setattr(meds, "insert_note", _fail_insert_note)

    out = await meds.save_care_document(FakeCtx(), "emergency", "short body")
    assert out == (
        "timeline_display_name is not set - ask Jordan what name to use before generating"
    )


@pytest.mark.asyncio
async def test_save_care_document_budget_gate_refuses_oversized_emergency(monkeypatch):
    monkeypatch.setattr(
        meds,
        "get_medication_profile",
        lambda *a, **kw: _async_return(
            MedicationProfile(org_id=ORG_ID, timeline_display_name="Ellie")
        ),
    )

    def _fail_insert_note(*a, **kw):
        raise AssertionError("must not write when body is over budget")

    monkeypatch.setattr(meds, "insert_note", _fail_insert_note)

    body = "x" * 3000
    out = await meds.save_care_document(FakeCtx(), "emergency", body)
    assert "3000 chars" in out
    assert "over the one-page budget" in out


@pytest.mark.asyncio
async def test_save_care_document_budget_gate_allows_handoff_same_size(monkeypatch):
    """The char-budget gate stays emergency-only even at 3,000 chars. This
    body still carries the critical flag verbatim so the (now doc-type-
    agnostic) critical-flags gate doesn't confound what this test checks."""
    captured = _patch_successful_write(monkeypatch)
    body = f"{DEFAULT_CRITICAL_FLAG} " + "x" * 3000
    out = await meds.save_care_document(FakeCtx(), "handoff", body)
    assert "insert_note" in captured
    assert "created" in out


@pytest.mark.asyncio
async def test_save_care_document_no_critical_flags_gate_refuses_when_care_none(monkeypatch):
    """No care profile at all — the emergency sheet has nothing to lead with,
    so the tool must refuse before ever looking at body content."""
    monkeypatch.setattr(
        meds,
        "get_medication_profile",
        lambda *a, **kw: _async_return(
            MedicationProfile(org_id=ORG_ID, timeline_display_name="Ellie")
        ),
    )
    monkeypatch.setattr(meds, "get_care_profile", lambda *a, **kw: _async_return(None))

    def _fail_insert_note(*a, **kw):
        raise AssertionError("must not write when there is no care profile")

    monkeypatch.setattr(meds, "insert_note", _fail_insert_note)

    out = await meds.save_care_document(FakeCtx(), "emergency", "one-page emergency body")

    assert out == (
        "Not written: the care profile has no critical_flags. The emergency sheet "
        "must lead with the QT warning - confirm the critical flags with Jordan first."
    )


@pytest.mark.asyncio
async def test_save_care_document_no_critical_flags_gate_refuses_when_flags_empty(monkeypatch):
    """A care profile exists but critical_flags is empty — same refusal as no
    profile at all; an emergency sheet must never ship with no QT warning."""
    care = CareProfile(org_id=ORG_ID, diagnoses=["Long QT syndrome"], critical_flags=[])
    monkeypatch.setattr(
        meds,
        "get_medication_profile",
        lambda *a, **kw: _async_return(
            MedicationProfile(org_id=ORG_ID, timeline_display_name="Ellie")
        ),
    )
    monkeypatch.setattr(meds, "get_care_profile", lambda *a, **kw: _async_return(care))

    def _fail_insert_note(*a, **kw):
        raise AssertionError("must not write when critical_flags is empty")

    monkeypatch.setattr(meds, "insert_note", _fail_insert_note)

    out = await meds.save_care_document(FakeCtx(), "emergency", "one-page emergency body")

    assert out == (
        "Not written: the care profile has no critical_flags. The emergency sheet "
        "must lead with the QT warning - confirm the critical flags with Jordan first."
    )


@pytest.mark.asyncio
async def test_save_care_document_no_critical_flags_gate_applies_to_handoff(monkeypatch):
    """Jordan decided the empty-critical_flags refusal now applies to the
    handoff too, not just the emergency sheet. Zero-write proof via the
    AssertionError-raising insert_note stand-in."""
    care = CareProfile(org_id=ORG_ID, diagnoses=["Long QT syndrome"], critical_flags=[])
    monkeypatch.setattr(
        meds,
        "get_medication_profile",
        lambda *a, **kw: _async_return(
            MedicationProfile(org_id=ORG_ID, timeline_display_name="Ellie")
        ),
    )
    monkeypatch.setattr(meds, "get_care_profile", lambda *a, **kw: _async_return(care))

    def _fail_insert_note(*a, **kw):
        raise AssertionError("must not write a handoff when critical_flags is empty")

    monkeypatch.setattr(meds, "insert_note", _fail_insert_note)

    out = await meds.save_care_document(FakeCtx(), "handoff", "handoff body, no flags on file")

    assert out == (
        "Not written: the care profile has no critical_flags. The emergency sheet "
        "must lead with the QT warning - confirm the critical flags with Jordan first."
    )


@pytest.mark.asyncio
async def test_save_care_document_critical_flag_gate_refuses_when_flag_missing(monkeypatch):
    """A missing (or reworded/paraphrased) critical flag must refuse the write
    entirely — the flag never appears as a substring of a paraphrase."""
    flag = (
        "Congenital Long QT — avoid QT-prolonging medications (CredibleMeds list); "
        "confirm any new drug with cardiology."
    )
    care = CareProfile(org_id=ORG_ID, critical_flags=[flag])
    _patch_successful_write(monkeypatch, care=care)

    def _fail_insert_note(*a, **kw):
        raise AssertionError("must not write when a critical flag is missing")

    monkeypatch.setattr(meds, "insert_note", _fail_insert_note)

    body = "CRITICAL: Congenital Long QT syndrome — avoid QT-prolonging meds. Confirm with cards."
    out = await meds.save_care_document(FakeCtx(), "emergency", body)

    assert out == (
        f"Not written: the critical flag '{flag}' must appear in the document word "
        "for word. Rewrite the body and include it verbatim - critical flags are "
        "never cut or paraphrased."
    )


@pytest.mark.asyncio
async def test_save_care_document_critical_flag_gate_allows_when_flag_present(monkeypatch):
    flag = "Congenital Long QT — avoid QT-prolonging medications (CredibleMeds list)."
    care = CareProfile(org_id=ORG_ID, critical_flags=[flag])
    captured = _patch_successful_write(monkeypatch, care=care)

    body = f"CRITICAL: {flag}\n\nRest of the one-pager follows."
    out = await meds.save_care_document(FakeCtx(), "emergency", body)

    assert "insert_note" in captured
    assert "created" in out


@pytest.mark.asyncio
async def test_save_care_document_critical_flag_gate_applies_to_handoff(monkeypatch):
    """Jordan decided the verbatim critical-flags gate now applies to the
    handoff too. A missing flag refuses the write, no budget gate involved.
    Zero-write proof via the AssertionError-raising insert_note stand-in."""
    flag = "Congenital Long QT — avoid QT-prolonging medications (CredibleMeds list)."
    care = CareProfile(org_id=ORG_ID, critical_flags=[flag])
    _patch_successful_write(monkeypatch, care=care)

    def _fail_insert_note(*a, **kw):
        raise AssertionError("must not write a handoff when a critical flag is missing")

    monkeypatch.setattr(meds, "insert_note", _fail_insert_note)

    body = "Handoff body that never mentions the flag at all."
    out = await meds.save_care_document(FakeCtx(), "handoff", body)

    assert out == (
        f"Not written: the critical flag '{flag}' must appear in the document word "
        "for word. Rewrite the body and include it verbatim - critical flags are "
        "never cut or paraphrased."
    )


@pytest.mark.asyncio
async def test_save_care_document_success_writes_and_upserts_hash_bundle(monkeypatch):
    captured = _patch_successful_write(monkeypatch)
    body = f"one-page emergency body. {DEFAULT_CRITICAL_FLAG}"
    out = await meds.save_care_document(FakeCtx(), "emergency", body)

    assert "insert_note" in captured
    note_kwargs = captured["insert_note"]
    assert note_kwargs["org_id"] == ORG_ID
    assert note_kwargs["note_type"] == "care_document"
    assert note_kwargs["frontmatter"]["type"] == "care-document"
    assert note_kwargs["frontmatter"]["doc_type"] == "emergency"
    assert note_kwargs["frontmatter"]["tags"] == ["health", "care-document"]
    assert note_kwargs["sync_status"] == "pending_export"

    expected_title = "Ellie - Emergency One-Pager - 2026-07-25"
    assert note_kwargs["title"] == expected_title
    assert note_kwargs["vault_path"] == f"Health/Documents/{expected_title}.md"
    assert expected_title in out

    upserted = captured["upsert_care_document"]
    assert upserted["org_id"] == ORG_ID
    assert upserted["doc_type"] == "emergency"
    assert upserted["note_title"] == expected_title
    bundle = json.loads(upserted["source_hash"])
    assert "total" in bundle
    assert "sections" in bundle


@pytest.mark.asyncio
async def test_save_care_document_title_uses_handoff_label(monkeypatch):
    captured = _patch_successful_write(monkeypatch)
    body = f"handoff body. {DEFAULT_CRITICAL_FLAG}"
    await meds.save_care_document(FakeCtx(), "handoff", body)
    expected_title = "Ellie - Caregiver Handoff - 2026-07-25"
    assert captured["insert_note"]["title"] == expected_title


@pytest.mark.asyncio
async def test_save_care_document_first_write_gets_no_version_suffix(monkeypatch):
    """No prior note at this same-day path — title must be the plain base
    title, no ' - vN' suffix."""
    captured = _patch_successful_write(monkeypatch, existing_paths=[])
    body = f"one-page emergency body. {DEFAULT_CRITICAL_FLAG}"
    await meds.save_care_document(FakeCtx(), "emergency", body)
    expected_title = "Ellie - Emergency One-Pager - 2026-07-25"
    assert captured["insert_note"]["title"] == expected_title
    assert captured["insert_note"]["vault_path"] == f"Health/Documents/{expected_title}.md"


@pytest.mark.asyncio
async def test_save_care_document_same_day_regeneration_gets_v2(monkeypatch):
    """Same-day regeneration: the exact base vault_path already exists (from
    the first generate today), so a second save must not collide with the
    (org_id, vault_path) unique constraint — it gets ' - v2' instead, and
    care_documents.note_title is updated to point at the v2 title."""
    base_title = "Ellie - Emergency One-Pager - 2026-07-25"
    captured = _patch_successful_write(
        monkeypatch, existing_paths=[f"Health/Documents/{base_title}.md"]
    )

    body = f"regenerated body. {DEFAULT_CRITICAL_FLAG}"
    out = await meds.save_care_document(FakeCtx(), "emergency", body)

    expected_title = f"{base_title} - v2"
    assert captured["insert_note"]["title"] == expected_title
    assert captured["insert_note"]["vault_path"] == f"Health/Documents/{expected_title}.md"
    assert expected_title in out
    assert captured["upsert_care_document"]["note_title"] == expected_title


@pytest.mark.asyncio
async def test_save_care_document_third_same_day_save_gets_v3(monkeypatch):
    """Both the base title and ' - v2' already exist — the next free number
    is v3."""
    base_title = "Ellie - Emergency One-Pager - 2026-07-25"
    captured = _patch_successful_write(
        monkeypatch,
        existing_paths=[
            f"Health/Documents/{base_title}.md",
            f"Health/Documents/{base_title} - v2.md",
        ],
    )

    body = f"regenerated again. {DEFAULT_CRITICAL_FLAG}"
    await meds.save_care_document(FakeCtx(), "emergency", body)

    expected_title = f"{base_title} - v3"
    assert captured["insert_note"]["title"] == expected_title
