from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.db.feedback import save_feedback

ORG_ID = "00000000-0000-0000-0000-000000000001"


def _mock_db():
    mock_query = MagicMock()
    mock_result = MagicMock(data=[{"id": "f1"}])
    mock_query.execute = AsyncMock(return_value=mock_result)
    mock_query.insert.return_value = mock_query
    mock_db = MagicMock()
    mock_db.table.return_value = mock_query
    return mock_db, mock_query


@pytest.mark.asyncio
async def test_save_feedback_full_payload():
    db, query = _mock_db()

    await save_feedback(
        db,
        org_id=ORG_ID,
        agent_slug="claw-main",
        conversation_id="conv-1",
        rating=4,
        note="useful answer",
        prompt_source="manual",
    )

    db.table.assert_called_once_with("feedback")
    payload = query.insert.call_args[0][0]
    assert payload["org_id"] == ORG_ID
    assert payload["agent_slug"] == "claw-main"
    assert payload["conversation_id"] == "conv-1"
    assert payload["rating"] == 4
    assert payload["note"] == "useful answer"
    assert payload["prompt_source"] == "manual"


@pytest.mark.asyncio
async def test_save_feedback_drops_none_fields():
    db, query = _mock_db()

    await save_feedback(
        db,
        org_id=ORG_ID,
        agent_slug="claw-main",
        conversation_id=None,
        rating=5,
        note=None,
        prompt_source="weekly_review",
    )

    payload = query.insert.call_args[0][0]
    assert "conversation_id" not in payload
    assert "note" not in payload
    assert payload["rating"] == 5
    assert payload["prompt_source"] == "weekly_review"


@pytest.mark.asyncio
async def test_save_feedback_low_rating():
    db, query = _mock_db()

    await save_feedback(
        db,
        org_id=ORG_ID,
        agent_slug="claw-main",
        conversation_id="conv-2",
        rating=1,
        note="missed the question",
        prompt_source="manual",
    )

    payload = query.insert.call_args[0][0]
    assert payload["rating"] == 1
    assert payload["note"] == "missed the question"
