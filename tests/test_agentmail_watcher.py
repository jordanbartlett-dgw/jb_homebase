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
    def __init__(self, items):
        self.items = items
        self.calls: list[dict] = []

    async def list(self, *, inbox_id: str, limit: int):
        self.calls.append({"inbox_id": inbox_id, "limit": limit})
        # API returns newest first
        newest_first = sorted(self.items, key=lambda m: m.timestamp, reverse=True)
        return SimpleNamespace(messages=newest_first[:limit])


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
    assert api.calls[0]["limit"] == 1


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
    client, _api = _fake_client(items)
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
