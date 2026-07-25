from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

SESSION_JSON = {
    "apiUrl": "https://api.fastmail.com/jmap/api/",
    "primaryAccounts": {"urn:ietf:params:jmap:mail": "u123"},
}


def _email(email_id: str, received_at: str, sender: str, subject: str) -> dict:
    return {
        "id": email_id,
        "receivedAt": received_at,
        "from": [{"name": "", "email": sender}],
        "subject": subject,
        "preview": f"preview of {subject}",
    }


def _api_json(emails: list[dict]) -> dict:
    return {
        "methodResponses": [
            ["Email/query", {"ids": [e["id"] for e in emails]}, "0"],
            ["Email/get", {"list": emails}, "1"],
        ]
    }


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        pass


def _install_fake_httpx(monkeypatch, api_json: dict) -> dict:
    """Replace httpx.AsyncClient in the fastmail module. Returns a call recorder."""
    calls: dict = {"get": [], "post": []}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, headers=None):
            calls["get"].append({"url": url, "headers": headers})
            return _FakeResponse(SESSION_JSON)

        async def post(self, url, headers=None, json=None):
            calls["post"].append({"url": url, "headers": headers, "json": json})
            return _FakeResponse(api_json)

    monkeypatch.setattr("jordan_claw.events.fastmail.httpx.AsyncClient", FakeAsyncClient)
    return calls


def _settings(token: str = "jmap-token") -> MagicMock:
    settings = MagicMock()
    settings.fastmail_api_token = token
    return settings


async def test_empty_token_skips_without_http(monkeypatch):
    from jordan_claw.events.fastmail import poll_fastmail

    calls = _install_fake_httpx(monkeypatch, _api_json([]))
    with patch("jordan_claw.events.fastmail.process_event", new=AsyncMock()) as mock_proc:
        processed = await poll_fastmail(MagicMock(), _settings(token=""))

    assert processed == 0
    assert calls["get"] == []
    assert calls["post"] == []
    mock_proc.assert_not_awaited()


async def test_first_poll_initializes_cursor_without_firing(monkeypatch):
    from jordan_claw.events.fastmail import poll_fastmail

    newest = _email("m9", "2026-07-04T12:00:00Z", "a@b.co", "Latest")
    calls = _install_fake_httpx(monkeypatch, _api_json([newest]))

    with (
        patch("jordan_claw.events.fastmail.get_cursor", new=AsyncMock(return_value={})),
        patch("jordan_claw.events.fastmail.save_cursor", new=AsyncMock()) as mock_save,
        patch("jordan_claw.events.fastmail.process_event", new=AsyncMock()) as mock_proc,
    ):
        processed = await poll_fastmail(MagicMock(), _settings())

    assert processed == 0
    mock_proc.assert_not_awaited()
    mock_save.assert_awaited_once()
    _db, source, cursor = mock_save.call_args.args
    assert source == "fastmail-email"
    assert cursor == {"after": "2026-07-04T12:00:00Z", "last_id": "m9"}

    # First poll queries without an "after" filter (no backfill storm:
    # newest-first, limit 1 — it only wants the newest email as the seed)
    query_args = calls["post"][0]["json"]["methodCalls"][0][1]
    assert "filter" not in query_args
    assert query_args["limit"] == 1
    assert query_args["sort"] == [{"property": "receivedAt", "isAscending": False}]


async def test_two_new_emails_fire_process_event_and_advance_cursor(monkeypatch):
    from jordan_claw.events.fastmail import poll_fastmail

    cursor = {"after": "2026-07-04T12:00:00Z", "last_id": "m9"}
    # Cursor-filtered query sorts ascending, so the server returns oldest first
    emails = [
        # Cursor email echoed back (JMAP "after" is inclusive): must be skipped
        _email("m9", "2026-07-04T12:00:00Z", "a@b.co", "Latest"),
        _email("m10", "2026-07-04T12:10:00Z", "bob@x.co", "First"),
        _email("m11", "2026-07-04T12:20:00Z", "carol@x.co", "Second"),
    ]
    calls = _install_fake_httpx(monkeypatch, _api_json(emails))

    with (
        patch(
            "jordan_claw.events.fastmail.get_cursor",
            new=AsyncMock(return_value=cursor),
        ),
        patch("jordan_claw.events.fastmail.save_cursor", new=AsyncMock()) as mock_save,
        patch("jordan_claw.events.fastmail.process_event", new=AsyncMock()) as mock_proc,
    ):
        db = MagicMock()
        settings = _settings()
        processed = await poll_fastmail(db, settings)

    assert processed == 2
    assert mock_proc.await_count == 2

    # Oldest first, payload carries from/subject/snippet
    first_kwargs = mock_proc.call_args_list[0].kwargs
    assert first_kwargs["source"] == "fastmail-email"
    assert first_kwargs["payload"] == {
        "from": "bob@x.co",
        "subject": "First",
        "snippet": "preview of First",
    }
    second_kwargs = mock_proc.call_args_list[1].kwargs
    assert second_kwargs["payload"]["from"] == "carol@x.co"
    assert second_kwargs["settings"] is settings

    # Cursor advances to the newest email
    _db, source, new_cursor = mock_save.call_args.args
    assert source == "fastmail-email"
    assert new_cursor == {"after": "2026-07-04T12:20:00Z", "last_id": "m11"}

    # Query used the stored cursor as the "after" filter, sorted ascending so
    # a >limit burst truncates to the oldest emails (rest arrive next poll)
    query_args = calls["post"][0]["json"]["methodCalls"][0][1]
    assert query_args["filter"] == {"after": "2026-07-04T12:00:00Z"}
    assert query_args["accountId"] == "u123"
    assert query_args["sort"] == [{"property": "receivedAt", "isAscending": True}]


async def test_burst_over_limit_paginates_without_loss(monkeypatch):
    """25 emails past the cursor: process the oldest 20, park the cursor at
    email 20 so the remaining 5 arrive naturally on the next poll."""
    from jordan_claw.events.fastmail import poll_fastmail

    cursor = {"after": "2026-07-04T12:00:00Z", "last_id": "m0"}
    # Server holds m1..m25 past the cursor; asc sort + limit 20 means it
    # returns only the oldest 20 (m1..m20).
    returned = [
        _email(f"m{i}", f"2026-07-04T12:{i:02d}:00Z", f"s{i}@x.co", f"Mail {i}")
        for i in range(1, 21)
    ]
    _install_fake_httpx(monkeypatch, _api_json(returned))

    with (
        patch(
            "jordan_claw.events.fastmail.get_cursor",
            new=AsyncMock(return_value=cursor),
        ),
        patch("jordan_claw.events.fastmail.save_cursor", new=AsyncMock()) as mock_save,
        patch("jordan_claw.events.fastmail.process_event", new=AsyncMock()) as mock_proc,
    ):
        processed = await poll_fastmail(MagicMock(), _settings())

    assert processed == 20
    assert mock_proc.await_count == 20
    assert mock_proc.call_args_list[0].kwargs["payload"]["subject"] == "Mail 1"
    assert mock_proc.call_args_list[-1].kwargs["payload"]["subject"] == "Mail 20"

    # Cursor parks at email #20, not past the unfetched m21..m25: the next
    # poll's "after" filter picks up exactly those five.
    _db, source, new_cursor = mock_save.call_args.args
    assert source == "fastmail-email"
    assert new_cursor == {"after": "2026-07-04T12:20:00Z", "last_id": "m20"}
