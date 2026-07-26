from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


def _item(message_id: str, ts: str, sender: str, subject: str, labels: list[str] | None = None):
    return SimpleNamespace(
        message_id=message_id,
        thread_id=f"th-{message_id}",
        timestamp=datetime.fromisoformat(ts),
        from_=sender,
        subject=subject,
        preview=f"preview of {subject}",
        labels=labels if labels is not None else ["received", "unread"],
    )


class _FakeMessagesApi:
    """Server-side filtering fake: honors labels/after/ascending like the
    real AgentMail API, so tests assert the parameters we actually send
    rather than re-filtering client side."""

    def __init__(self, items):
        self.items = items
        self.calls: list[dict] = []

    async def list(
        self,
        *,
        inbox_id: str,
        limit: int,
        labels: list[str] | None = None,
        after=None,
        ascending: bool | None = None,
    ):
        self.calls.append(
            {
                "inbox_id": inbox_id,
                "limit": limit,
                "labels": labels,
                "after": after,
                "ascending": ascending,
            }
        )
        rows = self.items
        if labels is not None:
            rows = [m for m in rows if set(labels) & set(m.labels or [])]
        if after is not None:
            rows = [m for m in rows if m.timestamp >= after]
        rows = sorted(rows, key=lambda m: m.timestamp, reverse=not ascending)
        return SimpleNamespace(messages=rows[:limit])


def _fake_client(items):
    api = _FakeMessagesApi(items)
    return SimpleNamespace(inboxes=SimpleNamespace(messages=api)), api


def _settings(key: str = "am-key") -> MagicMock:
    settings = MagicMock()
    settings.agentmail_api_key = key
    settings.agentmail_inbox_id = "jordanb@agentmail.to"
    return settings


async def test_empty_key_skips_without_api_call():
    from jordan_claw.events.agentmail import poll_agentmail

    with patch("jordan_claw.events.agentmail.process_event", new=AsyncMock()) as mock_proc:
        processed = await poll_agentmail(MagicMock(), _settings(key=""))

    assert processed == 0
    mock_proc.assert_not_awaited()


async def test_first_poll_seeds_cursor_without_firing():
    from jordan_claw.events.agentmail import poll_agentmail

    client, api = _fake_client([_item("m1", "2026-07-25T17:23:05+00:00", "a@b.co", "Old")])
    with (
        patch("jordan_claw.events.agentmail.get_agentmail_client", return_value=client),
        patch("jordan_claw.events.agentmail.get_cursor", new=AsyncMock(return_value={})),
        patch("jordan_claw.events.agentmail.save_cursor", new=AsyncMock()) as mock_save,
        patch("jordan_claw.events.agentmail.process_event", new=AsyncMock()) as mock_proc,
    ):
        processed = await poll_agentmail(MagicMock(), _settings())

    assert processed == 0
    mock_proc.assert_not_awaited()
    _db, source, cursor = mock_save.call_args.args
    assert source == "agentmail-email"
    assert cursor == {"after": "2026-07-25T17:23:05+00:00", "last_id": "m1"}
    # First poll: newest-first, limit 1, filtered server-side to received mail.
    assert api.calls[0] == {
        "inbox_id": "jordanb@agentmail.to",
        "limit": 1,
        "labels": ["received"],
        "after": None,
        "ascending": None,
    }


async def test_new_received_messages_fire_oldest_first_and_advance_cursor():
    from jordan_claw.events.agentmail import poll_agentmail

    cursor = {"after": "2026-07-25T17:23:05+00:00", "last_id": "m1"}
    items = [
        _item("m1", "2026-07-25T17:23:05+00:00", "a@b.co", "Seen"),
        _item("m2", "2026-07-25T18:00:00+00:00", "bob@x.co", "First"),
        _item("m3", "2026-07-25T19:00:00+00:00", "carol@x.co", "Second"),
        # Outbound mail must never re-enter the pipeline
        _item("m4", "2026-07-25T19:30:00+00:00", "jordanb@agentmail.to", "Reply", labels=["sent"]),
    ]
    client, api = _fake_client(items)
    with (
        patch("jordan_claw.events.agentmail.get_agentmail_client", return_value=client),
        patch("jordan_claw.events.agentmail.get_cursor", new=AsyncMock(return_value=cursor)),
        patch("jordan_claw.events.agentmail.save_cursor", new=AsyncMock()) as mock_save,
        patch("jordan_claw.events.agentmail.process_event", new=AsyncMock()) as mock_proc,
    ):
        settings = _settings()
        processed = await poll_agentmail(MagicMock(), settings)

    assert processed == 2
    first = mock_proc.call_args_list[0].kwargs
    assert first["source"] == "agentmail-email"
    assert first["payload"] == {
        "from": "bob@x.co",
        "subject": "First",
        "snippet": "preview of First",
    }
    assert mock_proc.call_args_list[1].kwargs["payload"]["from"] == "carol@x.co"

    _db, source, new_cursor = mock_save.call_args.args
    assert source == "agentmail-email"
    assert new_cursor == {"after": "2026-07-25T19:00:00+00:00", "last_id": "m3"}

    # Cursor poll asks the server for oldest-first, received-only, after the cursor.
    call = api.calls[0]
    assert call["labels"] == ["received"]
    assert call["ascending"] is True
    assert call["after"] == datetime.fromisoformat("2026-07-25T17:23:05+00:00")
    assert call["limit"] == 20


async def test_burst_over_limit_truncates_to_oldest_and_parks_at_newest_processed():
    """A burst bigger than POLL_LIMIT must not lose the oldest unprocessed
    messages: the server returns them oldest-first (truncating away the
    newest overflow), and the cursor parks at the newest one we actually
    processed, not the newest one that exists. The remainder arrives on the
    next poll."""
    from jordan_claw.events import agentmail as agentmail_module
    from jordan_claw.events.agentmail import poll_agentmail

    cursor = {"after": "2026-07-25T00:00:00+00:00", "last_id": "m0"}
    items = [_item("m0", "2026-07-25T00:00:00+00:00", "a@b.co", "Cursor")]
    # 25 new messages, one minute apart -- more than POLL_LIMIT (20).
    for i in range(1, 26):
        items.append(
            _item(f"m{i}", f"2026-07-25T01:{i:02d}:00+00:00", f"sender{i}@x.co", f"Msg {i}")
        )

    client, api = _fake_client(items)
    with (
        patch("jordan_claw.events.agentmail.get_agentmail_client", return_value=client),
        patch("jordan_claw.events.agentmail.get_cursor", new=AsyncMock(return_value=cursor)),
        patch("jordan_claw.events.agentmail.save_cursor", new=AsyncMock()) as mock_save,
        patch("jordan_claw.events.agentmail.process_event", new=AsyncMock()) as mock_proc,
    ):
        processed = await poll_agentmail(MagicMock(), _settings())

    # The server returns POLL_LIMIT (20) rows starting at the inclusive
    # cursor boundary: the cursor's own message (m0) plus the oldest 19 of
    # the burst. m0 is dropped by id, leaving 19 processed.
    assert agentmail_module.POLL_LIMIT == 20
    assert processed == 19
    processed_froms = [c.kwargs["payload"]["from"] for c in mock_proc.call_args_list]
    assert processed_froms == [f"sender{i}@x.co" for i in range(1, 20)]

    _db, source, new_cursor = mock_save.call_args.args
    assert source == "agentmail-email"
    # Cursor parks at the newest PROCESSED message (m19), not the newest
    # fetched or newest existing (m25) -- the overflow (m20..m25) is picked
    # up by the next poll.
    assert new_cursor == {"after": "2026-07-25T01:19:00+00:00", "last_id": "m19"}
