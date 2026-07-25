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
# save_care_document
# ---------------------------------------------------------------------------


def _patch_successful_write(monkeypatch, care=None, meds_profile=None, existing_paths=()):
    """Wire every dependency save_care_document needs for a real write, and
    return the captured insert_note/upsert_care_document call args.
    existing_paths simulates what get_vault_paths_with_prefix would find
    already in obsidian_notes — pass the exact same-day path to exercise the
    version-suffix collision handling."""
    captured: dict = {}

    meds_profile = meds_profile or MedicationProfile(org_id=ORG_ID, timeline_display_name="Ellie")
    care = care if care is not None else CareProfile(org_id=ORG_ID, diagnoses=["Long QT syndrome"])

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
    captured = _patch_successful_write(monkeypatch)
    body = "x" * 3000
    out = await meds.save_care_document(FakeCtx(), "handoff", body)
    assert "insert_note" in captured
    assert "created" in out


@pytest.mark.asyncio
async def test_save_care_document_success_writes_and_upserts_hash_bundle(monkeypatch):
    captured = _patch_successful_write(monkeypatch)
    out = await meds.save_care_document(FakeCtx(), "emergency", "one-page emergency body")

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
    await meds.save_care_document(FakeCtx(), "handoff", "handoff body")
    expected_title = "Ellie - Caregiver Handoff - 2026-07-25"
    assert captured["insert_note"]["title"] == expected_title


@pytest.mark.asyncio
async def test_save_care_document_first_write_gets_no_version_suffix(monkeypatch):
    """No prior note at this same-day path — title must be the plain base
    title, no ' - vN' suffix."""
    captured = _patch_successful_write(monkeypatch, existing_paths=[])
    await meds.save_care_document(FakeCtx(), "emergency", "one-page emergency body")
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

    out = await meds.save_care_document(FakeCtx(), "emergency", "regenerated body")

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

    await meds.save_care_document(FakeCtx(), "emergency", "regenerated again")

    expected_title = f"{base_title} - v3"
    assert captured["insert_note"]["title"] == expected_title
