"""Unit tests for the med-check timeline (Task 8) and care-document (Task 7)
stub plumbing — no API calls.

Exercises _build_toolset's capture-and-concatenate pattern for
create_timeline_note and save_care_document against TestModel (mirroring
test_evals_smoke.py's approach: test the harness/toolset wiring, never the
real TARGET_MODEL task fn, which would spend money). Also guards the
fixture-completeness invariant documented in evals/fixtures/med_check.py:
every FIXTURES entry must carry every fixture-driven tool key, or an
unexpected tool call KeyErrors the task fn and pydantic-evals silently drops
the case.
"""

from __future__ import annotations

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from evals.fixtures.med_check import FIXTURES, QT_CRITICAL_FLAG
from evals.tasks.med_check import _build_toolset, _compose_reply, _stub_care_document_refusal

SEIZURE_CRITICAL_FLAG = (
    "Seizure lasting over 5 minutes, or a second seizure within 30 minutes of the "
    "first, is a 911 call"
)

FIXTURE_DRIVEN_KEYS = (
    "normalize_medication",
    "fetch_fda_label",
    "get_medication_profile",
    "search_web",
    "fetch_article",
    "log_health_event",
    "amend_last_health_event",
    "get_health_events",
    "get_last_visit_date",
    "get_care_profile",
    "check_care_docs_current",
)


@pytest.mark.asyncio
async def test_create_timeline_note_captures_markdown_body() -> None:
    fixture = FIXTURES["timeline_three_months"]
    captured_notes: list[str] = []
    toolset = _build_toolset(fixture, captured_notes)

    agent = Agent(TestModel(call_tools=["create_timeline_note"]), toolsets=[toolset])
    result = await agent.run("prep the timeline")

    assert captured_notes, "create_timeline_note stub did not capture a note body"
    composed = _compose_reply(str(result.output), captured_notes)
    assert "===NOTE===" in composed
    assert captured_notes[-1] in composed


@pytest.mark.asyncio
async def test_no_note_written_returns_reply_unchanged() -> None:
    composed = _compose_reply("just a reply, no note", captured_notes=[])
    assert composed == "just a reply, no note"


@pytest.mark.asyncio
async def test_captured_notes_holder_is_per_call_not_shared() -> None:
    """Guards against reintroducing module-level state: two toolsets built from
    two separate holders must never see each other's captured note."""
    fixture = FIXTURES["timeline_three_months"]
    notes_a: list[str] = []
    notes_b: list[str] = []

    agent_a = Agent(
        TestModel(call_tools=["create_timeline_note"]), toolsets=[_build_toolset(fixture, notes_a)]
    )
    await agent_a.run("prep the timeline")

    assert notes_a
    assert notes_b == []


@pytest.mark.parametrize("fixture_name", list(FIXTURES))
def test_every_fixture_has_all_fixture_driven_keys(fixture_name: str) -> None:
    fixture = FIXTURES[fixture_name]
    missing = [key for key in FIXTURE_DRIVEN_KEYS if key not in fixture]
    assert not missing, f"fixture '{fixture_name}' missing keys: {missing}"


@pytest.mark.asyncio
async def test_save_care_document_captures_markdown_body() -> None:
    """TestModel's auto-generated tool args never carry the fixture's real
    critical_flags, so the (correct, prod-mirroring) gate would refuse a
    TestModel-driven call. Call the stub directly with a gate-passing body
    instead, same pattern as the other direct-call tests below."""
    fixture = FIXTURES["care_complete"]
    captured_notes: list[str] = []
    toolset = _build_toolset(fixture, captured_notes)

    body = f"CRITICAL: {QT_CRITICAL_FLAG} {SEIZURE_CRITICAL_FLAG}. Rest of the one-pager follows."
    tool_return = await toolset.tools["save_care_document"].function(
        doc_type="emergency", markdown_body=body
    )

    assert captured_notes == [body]
    composed = _compose_reply(tool_return, captured_notes)
    assert "===NOTE===" in composed
    assert captured_notes[-1] in composed


@pytest.mark.asyncio
async def test_save_care_document_stub_refuses_missing_critical_flag() -> None:
    """A body missing one of the fixture's critical_flags entries must be
    refused with the prod's exact refusal text, and nothing gets captured -
    this is the eval-stub-infidelity bug: the stub used to accept any body,
    denying the model the retry loop prod's real gate provides."""
    fixture = FIXTURES["care_complete"]
    captured_notes: list[str] = []
    toolset = _build_toolset(fixture, captured_notes)

    body = f"CRITICAL: {QT_CRITICAL_FLAG} Rest of the one-pager follows."  # missing seizure flag
    tool_return = await toolset.tools["save_care_document"].function(
        doc_type="handoff", markdown_body=body
    )

    assert tool_return == (
        f"Not written: the critical flag '{SEIZURE_CRITICAL_FLAG}' must appear in the "
        "document word for word. Rewrite the body and include it verbatim - "
        "critical flags are never cut or paraphrased."
    )
    assert captured_notes == []


@pytest.mark.asyncio
async def test_save_care_document_stub_refuses_empty_critical_flags() -> None:
    """A get_care_profile fixture with no critical_flags (or no parseable
    profile at all, e.g. a non-care fixture's placeholder) refuses the write
    outright, same as prod's empty-flags gate."""
    fixture = dict(FIXTURES["care_complete"])
    fixture["get_care_profile"] = 'Profile is complete.\n\n{"critical_flags": []}'
    captured_notes: list[str] = []
    toolset = _build_toolset(fixture, captured_notes)

    tool_return = await toolset.tools["save_care_document"].function(
        doc_type="emergency", markdown_body="anything at all"
    )

    assert tool_return == (
        "Not written: the care profile has no critical_flags. The emergency "
        "sheet must lead with the QT warning - confirm the critical flags "
        "with Jordan first."
    )
    assert captured_notes == []


def test_stub_care_document_refusal_budget_gate_emergency_only() -> None:
    """The char-budget gate mirrors prod: emergency over CARE_DOC_CHAR_BUDGET
    refuses before the critical-flags check ever runs; handoff has no such
    gate at any size."""
    oversized = "x" * 3000
    care_profile_fixture = FIXTURES["care_complete"]["get_care_profile"]

    refusal = _stub_care_document_refusal("emergency", oversized, care_profile_fixture)
    assert refusal is not None
    assert "3000 chars" in refusal
    assert "over the one-page budget" in refusal

    # Same oversized body on handoff hits the critical-flags gate instead,
    # since the budget gate is emergency-only and this body has no flags.
    handoff_refusal = _stub_care_document_refusal("handoff", oversized, care_profile_fixture)
    assert handoff_refusal is not None
    assert "over the one-page budget" not in handoff_refusal


def test_fixture_critical_flags_parses_json_tail() -> None:
    from evals.tasks.med_check import _fixture_critical_flags

    parsed = _fixture_critical_flags(FIXTURES["care_complete"]["get_care_profile"])
    assert parsed == [QT_CRITICAL_FLAG, SEIZURE_CRITICAL_FLAG]


def test_fixture_critical_flags_empty_for_non_care_placeholder() -> None:
    from evals.tasks.med_check import _fixture_critical_flags

    placeholder = FIXTURES["known_risk_ondansetron"]["get_care_profile"]
    assert _fixture_critical_flags(placeholder) == []


@pytest.mark.asyncio
async def test_get_care_profile_returns_fixture_value() -> None:
    fixture = FIXTURES["care_missing_seizure_plan"]
    toolset = _build_toolset(fixture, captured_notes=[])

    tool_return = await toolset.tools["get_care_profile"].function()

    assert tool_return == fixture["get_care_profile"]
    assert "seizure_plan" in tool_return


@pytest.mark.asyncio
async def test_check_care_docs_current_returns_fixture_value() -> None:
    fixture = FIXTURES["care_stale_after_save"]
    toolset = _build_toolset(fixture, captured_notes=[])

    tool_return = await toolset.tools["check_care_docs_current"].function()

    assert tool_return == fixture["check_care_docs_current"]
    assert "stale" in tool_return


@pytest.mark.asyncio
async def test_save_care_profile_returns_confirmation() -> None:
    fixture = FIXTURES["care_stale_after_save"]
    toolset = _build_toolset(fixture, captured_notes=[])

    tool_return = await toolset.tools["save_care_profile"].function(seizure_plan="updated plan")

    assert tool_return == "Care profile saved."
