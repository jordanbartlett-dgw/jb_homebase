from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.db.care import (
    get_care_document,
    get_care_profile,
    upsert_care_document,
    upsert_care_profile,
)
from jordan_claw.meds.models import CareContact, CareProfile

ORG_ID = "org-1"


def _mock_db(select_data=None):
    """Mock Supabase async client with chained query builder (same pattern as test_meds_profile)."""
    mock_result = MagicMock(data=select_data or [])

    mock_query = MagicMock()
    mock_query.execute = AsyncMock(return_value=mock_result)
    mock_query.limit.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.select.return_value = mock_query
    mock_query.upsert.return_value = mock_query

    mock_db = MagicMock()
    mock_db.table.return_value = mock_query
    return mock_db, mock_query


def test_empty_sections_reports_all_when_unset():
    profile = CareProfile(org_id="org-1")
    empty = profile.empty_sections()
    assert empty == [
        "diagnoses",
        "critical_flags",
        "seizure_plan",
        "baselines",
        "communication",
        "routines",
        "escalation",
        "contacts",
    ]


def test_empty_sections_partial():
    profile = CareProfile(
        org_id="org-1",
        diagnoses=["Long QT syndrome"],
        critical_flags=["avoid QT-prolonging meds"],
        seizure_plan="call 911 if seizure > 5 min",
    )
    empty = profile.empty_sections()
    assert "diagnoses" not in empty
    assert "critical_flags" not in empty
    assert "seizure_plan" not in empty
    assert "baselines" in empty
    assert "communication" in empty
    assert "routines" in empty
    assert "escalation" in empty
    assert "contacts" in empty


def test_empty_sections_empty_when_fully_populated():
    profile = CareProfile(
        org_id="org-1",
        diagnoses=["Long QT syndrome"],
        critical_flags=["avoid QT-prolonging meds"],
        seizure_plan="call 911 if seizure > 5 min",
        baselines="resting HR 70-90",
        communication="uses AAC device",
        routines="bedtime 8pm",
        escalation="call mom first, then cardiology",
        contacts=[CareContact(role="mom", name="Jane", phone="555-1234")],
    )
    assert profile.empty_sections() == []


@pytest.mark.asyncio
async def test_get_care_profile_returns_none_when_empty():
    db, _query = _mock_db(select_data=[])
    result = await get_care_profile(db, ORG_ID)
    assert result is None


@pytest.mark.asyncio
async def test_get_care_profile_returns_model():
    row = {
        "org_id": ORG_ID,
        "diagnoses": ["Long QT syndrome"],
        "critical_flags": [],
        "seizure_plan": None,
        "baselines": None,
        "communication": None,
        "routines": None,
        "escalation": None,
        "contacts": [],
    }
    db, _query = _mock_db(select_data=[row])
    result = await get_care_profile(db, ORG_ID)
    assert isinstance(result, CareProfile)
    assert result.diagnoses == ["Long QT syndrome"]
    db.table.assert_called_with("care_profiles")


@pytest.mark.asyncio
async def test_upsert_care_profile_seizure_plan_only_sends_provided_fields():
    """save(seizure_plan=...) must not clobber other sections. Assert the upsert
    payload contains only org_id, seizure_plan, updated_at."""
    db, query = _mock_db()
    await upsert_care_profile(
        db, ORG_ID, seizure_plan="call 911 if seizure > 5 min", baselines=None, contacts=None
    )
    sent = query.upsert.call_args[0][0]
    assert set(sent.keys()) == {"org_id", "seizure_plan", "updated_at"}
    assert sent["org_id"] == ORG_ID
    assert sent["seizure_plan"] == "call 911 if seizure > 5 min"
    assert "updated_at" in sent
    assert query.upsert.call_args.kwargs["on_conflict"] == "org_id"
    db.table.assert_called_with("care_profiles")


@pytest.mark.asyncio
async def test_get_care_document_returns_none_when_empty():
    db, _query = _mock_db(select_data=[])
    result = await get_care_document(db, ORG_ID, "emergency")
    assert result is None


@pytest.mark.asyncio
async def test_get_care_document_returns_row():
    row = {
        "org_id": ORG_ID,
        "doc_type": "emergency",
        "source_hash": "abc123",
        "note_title": "Emergency Sheet",
        "generated_at": "2026-07-25T00:00:00+00:00",
    }
    db, _query = _mock_db(select_data=[row])
    result = await get_care_document(db, ORG_ID, "emergency")
    assert result == row
    db.table.assert_called_with("care_documents")


@pytest.mark.asyncio
async def test_upsert_care_document_uses_composite_on_conflict():
    db, query = _mock_db()
    await upsert_care_document(
        db,
        ORG_ID,
        doc_type="handoff",
        source_hash="deadbeef",
        note_title="Handoff Sheet",
    )
    sent = query.upsert.call_args[0][0]
    assert sent["org_id"] == ORG_ID
    assert sent["doc_type"] == "handoff"
    assert sent["source_hash"] == "deadbeef"
    assert sent["note_title"] == "Handoff Sheet"
    assert "generated_at" in sent
    assert query.upsert.call_args.kwargs["on_conflict"] == "org_id,doc_type"
    db.table.assert_called_with("care_documents")
