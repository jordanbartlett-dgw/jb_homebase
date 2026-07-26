from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

TRIGGER_ROW = {
    "id": "t-1",
    "org_id": "org-1",
    "source": "fastmail-email",
    "name": "inbound_email_review",
    "enabled": True,
    "agent_slug": "claw-main",
    "prompt_template": "From: {from}. Subject: {subject}.",
    "filter": {},
    "created_at": "2026-07-04T00:00:00+00:00",
}


def _mock_db(data: list[dict] | None = None) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = data or []

    chain = MagicMock()
    chain.execute = AsyncMock(return_value=result)
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.upsert.return_value = chain
    db.table.return_value = chain
    return db


def _settings() -> MagicMock:
    settings = MagicMock()
    settings.tavily_api_key = "tv"
    settings.fastmail_username = "u"
    settings.fastmail_app_password = "p"
    settings.openai_api_key = "oa"
    settings.default_agent_slug = "claw-main"
    settings.agentmail_api_key = ""
    settings.agentmail_inbox_id = ""
    return settings


def _run_result(
    output: str,
    *,
    cost_usd: Decimal | None = Decimal("0.01"),
    input_tokens: int = 100,
    output_tokens: int = 50,
    duration_ms: int = 900,
) -> MagicMock:
    result = MagicMock()
    result.output = output
    result.cost_usd = cost_usd
    result.input_tokens = input_tokens
    result.output_tokens = output_tokens
    result.duration_ms = duration_ms
    return result


# --- render_prompt / SafeDict ---


def test_render_prompt_fills_known_keys():
    from jordan_claw.events.pipeline import render_prompt

    out = render_prompt(
        "From: {from}. Subject: {subject}.",
        {"from": "a@b.co", "subject": "Hi"},
    )
    assert out == "From: a@b.co. Subject: Hi."


def test_render_prompt_leaves_unknown_keys_intact():
    from jordan_claw.events.pipeline import render_prompt

    out = render_prompt("From: {from}. Odd: {unknown_key}.", {"from": "a@b.co"})
    assert out == "From: a@b.co. Odd: {unknown_key}."


# --- db accessors: trigger matching by source + enabled ---


async def test_get_triggers_filters_by_source_and_enabled():
    from jordan_claw.db.event_triggers import get_triggers

    db = _mock_db([TRIGGER_ROW])
    triggers = await get_triggers(db, "fastmail-email")

    assert len(triggers) == 1
    assert triggers[0].name == "inbound_email_review"
    assert triggers[0].agent_slug == "claw-main"

    chain = db.table.return_value
    db.table.assert_called_once_with("event_triggers")
    eq_calls = {call.args for call in chain.eq.call_args_list}
    assert ("source", "fastmail-email") in eq_calls
    assert ("enabled", True) in eq_calls


# --- process_event ---


async def test_process_event_runs_each_trigger_and_publishes():
    from jordan_claw.events.pipeline import process_event

    db = _mock_db()
    agent = MagicMock()

    with (
        patch(
            "jordan_claw.events.pipeline.get_triggers",
            new=AsyncMock(return_value=_triggers(2)),
        ),
        patch(
            "jordan_claw.events.pipeline.build_agent",
            new=AsyncMock(return_value=(agent, "model-x")),
        ) as mock_build,
        patch(
            "jordan_claw.events.pipeline.run_agent_instrumented",
            new=AsyncMock(return_value=_run_result("Heads up: invoice due.")),
        ) as mock_run,
        patch(
            "jordan_claw.events.pipeline.publish_proactive_message",
            new=AsyncMock(),
        ) as mock_publish,
        patch(
            "jordan_claw.events.pipeline.emitter.event_trigger_fired",
            new=AsyncMock(),
        ) as mock_emit,
    ):
        started = await process_event(
            db,
            source="fastmail-email",
            payload={"from": "a@b.co", "subject": "Invoice"},
            settings=_settings(),
        )

    assert started == 2
    assert mock_build.await_count == 2
    assert mock_run.await_count == 2
    run_kwargs = mock_run.call_args.kwargs
    assert run_kwargs["prompt"] == "From: a@b.co. Subject: Invoice."
    assert run_kwargs["channel"] == "webhook"
    assert run_kwargs["run_kind"].value == "event"
    assert mock_publish.await_count == 2
    publish_kwargs = mock_publish.call_args.kwargs
    assert publish_kwargs["content"] == "Heads up: invoice due."
    assert publish_kwargs["agent_slug"] == "claw-main"

    assert mock_emit.await_count == 2
    emit_kwargs = mock_emit.call_args.kwargs
    assert emit_kwargs["outcome"] == "fired"
    assert emit_kwargs["source"] == "fastmail-email"
    assert emit_kwargs["cost_usd"] == Decimal("0.01")
    assert emit_kwargs["input_tokens"] == 100
    assert emit_kwargs["output_tokens"] == 50
    assert emit_kwargs["duration_ms"] == 900
    assert emit_kwargs["org_id"] == "org-1"
    assert emit_kwargs["user_id"] is None


async def test_process_event_suppresses_nothing_to_send():
    from jordan_claw.events.pipeline import process_event

    db = _mock_db()

    with (
        patch(
            "jordan_claw.events.pipeline.get_triggers",
            new=AsyncMock(return_value=_triggers(1)),
        ),
        patch(
            "jordan_claw.events.pipeline.build_agent",
            new=AsyncMock(return_value=(MagicMock(), "model-x")),
        ),
        patch(
            "jordan_claw.events.pipeline.run_agent_instrumented",
            new=AsyncMock(
                return_value=_run_result(
                    "NOTHING_TO_SEND",
                    cost_usd=None,
                    input_tokens=10,
                    output_tokens=5,
                    duration_ms=200,
                )
            ),
        ),
        patch(
            "jordan_claw.events.pipeline.publish_proactive_message",
            new=AsyncMock(),
        ) as mock_publish,
        patch(
            "jordan_claw.events.pipeline.emitter.event_trigger_fired",
            new=AsyncMock(),
        ) as mock_emit,
    ):
        started = await process_event(
            db,
            source="fastmail-email",
            payload={"from": "noreply@spam.co", "subject": "sale"},
            settings=_settings(),
        )

    assert started == 1
    mock_publish.assert_not_awaited()
    mock_emit.assert_awaited_once()
    emit_kwargs = mock_emit.call_args.kwargs
    assert emit_kwargs["outcome"] == "nothing_to_send"
    assert emit_kwargs["cost_usd"] is None
    assert emit_kwargs["input_tokens"] == 10
    assert emit_kwargs["output_tokens"] == 5
    assert emit_kwargs["duration_ms"] == 200


async def test_event_deps_never_carry_email_send_creds():
    """Regression guard for the locked policy: autonomous (event) runs never
    send email. Even when settings has real AgentMail creds, the AgentDeps
    built for a triggered run must carry empty ones so the email tools
    degrade to NOT_CONFIGURED.
    """
    from jordan_claw.events.pipeline import process_event

    db = _mock_db()
    settings = _settings()
    settings.agentmail_api_key = "real-key"
    settings.agentmail_inbox_id = "real-inbox@agentmail.to"

    with (
        patch(
            "jordan_claw.events.pipeline.get_triggers",
            new=AsyncMock(return_value=_triggers(1)),
        ),
        patch(
            "jordan_claw.events.pipeline.build_agent",
            new=AsyncMock(return_value=(MagicMock(), "model-x")),
        ),
        patch(
            "jordan_claw.events.pipeline.run_agent_instrumented",
            new=AsyncMock(return_value=_run_result("ok")),
        ) as mock_run,
        patch(
            "jordan_claw.events.pipeline.publish_proactive_message",
            new=AsyncMock(),
        ),
    ):
        await process_event(
            db,
            source="fastmail-email",
            payload={"from": "a@b.co", "subject": "Invoice"},
            settings=settings,
        )

    deps = mock_run.call_args.kwargs["deps"]
    assert deps.agentmail_api_key == ""
    assert deps.agentmail_inbox_id == ""


async def test_process_event_continues_after_trigger_failure():
    from jordan_claw.events.pipeline import process_event

    db = _mock_db()

    with (
        patch(
            "jordan_claw.events.pipeline.get_triggers",
            new=AsyncMock(return_value=_triggers(2)),
        ),
        patch(
            "jordan_claw.events.pipeline.build_agent",
            new=AsyncMock(side_effect=[RuntimeError("boom"), (MagicMock(), "model-x")]),
        ),
        patch(
            "jordan_claw.events.pipeline.run_agent_instrumented",
            new=AsyncMock(return_value=_run_result("ok")),
        ),
        patch(
            "jordan_claw.events.pipeline.publish_proactive_message",
            new=AsyncMock(),
        ) as mock_publish,
    ):
        started = await process_event(
            db,
            source="fastmail-email",
            payload={},
            settings=_settings(),
        )

    assert started == 1
    assert mock_publish.await_count == 1


def _triggers(n: int):
    from jordan_claw.db.event_triggers import EventTrigger

    return [
        EventTrigger.model_validate({**TRIGGER_ROW, "id": f"t-{i}", "name": f"trig-{i}"})
        for i in range(n)
    ]


# --- webhook route ---


def _webhook_client() -> httpx.AsyncClient:
    from jordan_claw.main import app

    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _wire_app_state(secret: str) -> MagicMock:
    from jordan_claw.main import app

    settings = _settings()
    settings.claw_webhook_secret = secret
    app.state.settings = settings
    app.state.db = MagicMock()
    return settings


async def test_webhook_returns_503_when_secret_unconfigured():
    _wire_app_state(secret="")
    async with _webhook_client() as client:
        resp = await client.post(
            "/webhooks/fastmail-email",
            json={"subject": "x"},
            headers={"X-Claw-Secret": ""},
        )
    assert resp.status_code == 503


async def test_webhook_returns_401_on_wrong_secret():
    _wire_app_state(secret="right-secret")
    async with _webhook_client() as client:
        resp = await client.post(
            "/webhooks/fastmail-email",
            json={"subject": "x"},
            headers={"X-Claw-Secret": "wrong-secret"},
        )
    assert resp.status_code == 401


async def test_webhook_returns_401_on_missing_header():
    _wire_app_state(secret="right-secret")
    async with _webhook_client() as client:
        resp = await client.post("/webhooks/fastmail-email", json={"subject": "x"})
    assert resp.status_code == 401


async def test_webhook_accepts_and_spawns_background_task():
    from jordan_claw import main

    _wire_app_state(secret="right-secret")
    with patch("jordan_claw.main.process_event", new=AsyncMock(return_value=1)) as mock_proc:
        async with _webhook_client() as client:
            resp = await client.post(
                "/webhooks/fastmail-email",
                json={"subject": "Invoice", "from": "a@b.co"},
                headers={"X-Claw-Secret": "right-secret"},
            )
        await main.drain_pending_event_tasks()

    assert resp.status_code == 202
    assert resp.json() == {"accepted": True}
    mock_proc.assert_awaited_once()
    kwargs = mock_proc.call_args.kwargs
    assert kwargs["source"] == "fastmail-email"
    assert kwargs["payload"] == {"subject": "Invoice", "from": "a@b.co"}
