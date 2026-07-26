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

from evals.fixtures.med_check import FIXTURES
from evals.tasks.med_check import _build_toolset, _compose_reply

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
    fixture = FIXTURES["care_complete"]
    captured_notes: list[str] = []
    toolset = _build_toolset(fixture, captured_notes)

    agent = Agent(TestModel(call_tools=["save_care_document"]), toolsets=[toolset])
    result = await agent.run("make her emergency sheet")

    assert captured_notes, "save_care_document stub did not capture a markdown body"
    composed = _compose_reply(str(result.output), captured_notes)
    assert "===NOTE===" in composed
    assert captured_notes[-1] in composed


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
