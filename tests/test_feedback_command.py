from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.channels.telegram import _parse_feedback_args, handle_feedback_command

# --- Pure parser tests ---------------------------------------------------


def test_parse_basic_rating():
    assert _parse_feedback_args("/feedback 4") == (4, None, "manual")


def test_parse_rating_with_note():
    assert _parse_feedback_args("/feedback 4 useful answer") == (
        4,
        "useful answer",
        "manual",
    )


def test_parse_rating_with_multiword_note():
    assert _parse_feedback_args("/feedback 3 missed the point but tried hard") == (
        3,
        "missed the point but tried hard",
        "manual",
    )


def test_parse_weekly_rating():
    assert _parse_feedback_args("/feedback weekly 5") == (5, None, "weekly_review")


def test_parse_weekly_rating_with_note():
    assert _parse_feedback_args("/feedback weekly 5 great week with sage") == (
        5,
        "great week with sage",
        "weekly_review",
    )


def test_parse_weekly_case_insensitive():
    assert _parse_feedback_args("/feedback WEEKLY 4 ok")[2] == "weekly_review"


def test_parse_invalid_rating_zero():
    assert _parse_feedback_args("/feedback 0") is None


def test_parse_invalid_rating_six():
    assert _parse_feedback_args("/feedback 6") is None


def test_parse_invalid_non_digit():
    assert _parse_feedback_args("/feedback great") is None


def test_parse_missing_args():
    assert _parse_feedback_args("/feedback") is None


def test_parse_weekly_missing_rating():
    assert _parse_feedback_args("/feedback weekly") is None


def test_parse_weekly_invalid_rating():
    assert _parse_feedback_args("/feedback weekly 9") is None


# --- Handler tests -------------------------------------------------------

ORG_ID = "00000000-0000-0000-0000-000000000001"


def _mock_message(text: str) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.answer = AsyncMock()
    return msg


@pytest.mark.asyncio
async def test_handle_feedback_happy_path():
    msg = _mock_message("/feedback 4 useful")
    db = MagicMock()

    with (
        patch(
            "jordan_claw.channels.telegram.most_recent_agent",
            new=AsyncMock(return_value="claw-main"),
        ),
        patch(
            "jordan_claw.channels.telegram.most_recent_conversation_id",
            new=AsyncMock(return_value="conv-9"),
        ),
        patch(
            "jordan_claw.channels.telegram.save_feedback",
            new=AsyncMock(),
        ) as save_mock,
        patch(
            "jordan_claw.channels.telegram.emitter",
        ) as emitter_mock,
    ):
        emitter_mock.feedback_submitted = AsyncMock()
        await handle_feedback_command(
            msg,
            db=db,
            default_org_id=ORG_ID,
            default_agent_slug="claw-main",
        )

    save_mock.assert_awaited_once()
    kwargs = save_mock.await_args.kwargs
    assert kwargs["org_id"] == ORG_ID
    assert kwargs["agent_slug"] == "claw-main"
    assert kwargs["conversation_id"] == "conv-9"
    assert kwargs["rating"] == 4
    assert kwargs["note"] == "useful"
    assert kwargs["prompt_source"] == "manual"

    emitter_mock.feedback_submitted.assert_awaited_once()
    emit_kwargs = emitter_mock.feedback_submitted.await_args.kwargs
    assert emit_kwargs["agent_slug"] == "claw-main"
    assert emit_kwargs["rating"] == 4
    assert emit_kwargs["has_note"] is True
    assert emit_kwargs["prompt_source"] == "manual"
    assert emit_kwargs["conversation_id"] == "conv-9"

    msg.answer.assert_awaited_once_with("Got it. Rated 4/5.")


@pytest.mark.asyncio
async def test_handle_feedback_weekly():
    msg = _mock_message("/feedback weekly 5 great week")
    db = MagicMock()

    with (
        patch(
            "jordan_claw.channels.telegram.most_recent_agent",
            new=AsyncMock(return_value="claw-main"),
        ),
        patch(
            "jordan_claw.channels.telegram.most_recent_conversation_id",
            new=AsyncMock(return_value="conv-9"),
        ),
        patch(
            "jordan_claw.channels.telegram.save_feedback",
            new=AsyncMock(),
        ) as save_mock,
        patch(
            "jordan_claw.channels.telegram.emitter",
        ) as emitter_mock,
    ):
        emitter_mock.feedback_submitted = AsyncMock()
        await handle_feedback_command(
            msg,
            db=db,
            default_org_id=ORG_ID,
            default_agent_slug="claw-main",
        )

    kwargs = save_mock.await_args.kwargs
    assert kwargs["prompt_source"] == "weekly_review"
    assert kwargs["rating"] == 5
    assert kwargs["note"] == "great week"


@pytest.mark.asyncio
async def test_handle_feedback_falls_back_to_default_agent():
    msg = _mock_message("/feedback 4")
    db = MagicMock()

    with (
        patch(
            "jordan_claw.channels.telegram.most_recent_agent",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "jordan_claw.channels.telegram.most_recent_conversation_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "jordan_claw.channels.telegram.save_feedback",
            new=AsyncMock(),
        ) as save_mock,
        patch(
            "jordan_claw.channels.telegram.emitter",
        ) as emitter_mock,
    ):
        emitter_mock.feedback_submitted = AsyncMock()
        await handle_feedback_command(
            msg,
            db=db,
            default_org_id=ORG_ID,
            default_agent_slug="claw-main",
        )

    kwargs = save_mock.await_args.kwargs
    assert kwargs["agent_slug"] == "claw-main"
    assert kwargs["conversation_id"] is None
    assert kwargs["note"] is None


@pytest.mark.asyncio
async def test_handle_feedback_invalid_args_shows_usage():
    msg = _mock_message("/feedback wat")
    db = MagicMock()

    with (
        patch(
            "jordan_claw.channels.telegram.save_feedback",
            new=AsyncMock(),
        ) as save_mock,
    ):
        await handle_feedback_command(
            msg,
            db=db,
            default_org_id=ORG_ID,
            default_agent_slug="claw-main",
        )

    save_mock.assert_not_awaited()
    msg.answer.assert_awaited_once()
    assert "Usage" in msg.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_handle_feedback_missing_args_shows_usage():
    msg = _mock_message("/feedback")
    db = MagicMock()

    with patch(
        "jordan_claw.channels.telegram.save_feedback",
        new=AsyncMock(),
    ) as save_mock:
        await handle_feedback_command(
            msg,
            db=db,
            default_org_id=ORG_ID,
            default_agent_slug="claw-main",
        )

    save_mock.assert_not_awaited()
    msg.answer.assert_awaited_once()
