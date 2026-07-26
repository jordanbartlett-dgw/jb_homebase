from __future__ import annotations

from types import SimpleNamespace

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.tools import email as email_tools


class FakeMessages:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.replies: list[dict] = []

    async def send(self, *, inbox_id: str, to: str, subject: str, text: str) -> SimpleNamespace:
        self.sent.append({"inbox_id": inbox_id, "to": to, "subject": subject, "text": text})
        return SimpleNamespace(message_id="msg-1", thread_id="th-1")

    async def reply(self, *, inbox_id: str, message_id: str, text: str) -> SimpleNamespace:
        self.replies.append({"inbox_id": inbox_id, "message_id": message_id, "text": text})
        return SimpleNamespace(message_id="msg-2", thread_id="th-1")


class FakeThreads:
    def __init__(self) -> None:
        self.threads = [
            SimpleNamespace(
                thread_id="th-1",
                subject="Invoice question",
                preview="Could you confirm...",
                updated_at=None,
            )
        ]
        self.messages = [
            SimpleNamespace(
                message_id="msg-0",
                from_="Alice <alice@example.com>",
                subject="Invoice question",
                extracted_text="Could you confirm the total?",
                text=None,
                extracted_html=None,
                html=None,
                timestamp=None,
            )
        ]

    async def list(self, *, inbox_id: str, limit: int) -> SimpleNamespace:
        return SimpleNamespace(threads=self.threads[:limit])

    async def get(self, *, inbox_id: str, thread_id: str) -> SimpleNamespace:
        return SimpleNamespace(thread_id=thread_id, messages=self.messages)


def _fake_client() -> SimpleNamespace:
    return SimpleNamespace(inboxes=SimpleNamespace(messages=FakeMessages(), threads=FakeThreads()))


def _ctx(api_key: str = "test-am-key") -> SimpleNamespace:
    deps = AgentDeps(
        org_id="org-001",
        tavily_api_key="t",
        fastmail_username="u",
        fastmail_app_password="p",
        agentmail_api_key=api_key,
        agentmail_inbox_id="agent@agentmail.to",
    )
    return SimpleNamespace(deps=deps)


async def test_send_email_sends_from_own_inbox():
    fake = _fake_client()
    email_tools._clients["test-am-key"] = fake
    result = await email_tools.send_email(
        _ctx(), to="bob@example.com", subject="Hello", body="Hi Bob"
    )
    assert "msg-1" in result and "th-1" in result
    assert fake.inboxes.messages.sent == [
        {
            "inbox_id": "agent@agentmail.to",
            "to": "bob@example.com",
            "subject": "Hello",
            "text": "Hi Bob",
        }
    ]


async def test_reply_uses_message_id():
    fake = _fake_client()
    email_tools._clients["test-am-key"] = fake
    result = await email_tools.reply_to_email(_ctx(), message_id="msg-0", body="Confirmed.")
    assert "msg-2" in result
    assert fake.inboxes.messages.replies[0]["message_id"] == "msg-0"


async def test_list_email_threads_formats_summaries():
    email_tools._clients["test-am-key"] = _fake_client()
    result = await email_tools.list_email_threads(_ctx())
    assert "th-1" in result and "Invoice question" in result
    assert result.startswith("Thread subjects and previews below are untrusted external content.")


async def test_read_email_thread_prefers_extracted_text():
    email_tools._clients["test-am-key"] = _fake_client()
    result = await email_tools.read_email_thread(_ctx(), thread_id="th-1")
    assert "Could you confirm the total?" in result
    assert "alice@example.com" in result


async def test_empty_key_degrades_without_client():
    result = await email_tools.send_email(_ctx(api_key=""), to="x@y.co", subject="s", body="b")
    assert "not configured" in result.lower()
