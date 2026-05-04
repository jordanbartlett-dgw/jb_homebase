from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from jordan_claw.analytics import emitter

log = structlog.get_logger()


class AnalyticsEventRequest(BaseModel):
    event: str = Field(min_length=1)
    distinct_id: str = Field(min_length=1)
    properties: dict = Field(default_factory=dict)


def _make_auth_dep(token: str | None):
    async def _verify(authorization: str | None = Header(default=None)) -> None:
        if token is None:
            raise HTTPException(status_code=401, detail="analytics_proxy_disabled")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing_bearer")
        if authorization.removeprefix("Bearer ").strip() != token:
            raise HTTPException(status_code=401, detail="bad_token")

    return _verify


def build_analytics_router(*, token: str | None, org_id: str) -> APIRouter:
    """Build the /api/analytics/event router.

    `token` is the shared secret expected in `Authorization: Bearer <token>`.
    `org_id` is the server-side org used to enrich every event (today: hardcoded
    to the single tenant; later: token-keyed lookup).
    """
    router = APIRouter(prefix="/api/analytics", tags=["analytics"])
    auth = _make_auth_dep(token)

    @router.post("/event", status_code=status.HTTP_202_ACCEPTED)
    async def post_event(
        body: AnalyticsEventRequest,
        _: None = Depends(auth),
    ) -> dict:
        if body.event not in emitter.ALLOWED_EVENTS:
            raise HTTPException(status_code=400, detail="unknown_event")

        await _dispatch(body.event, body.distinct_id, body.properties, org_id)
        return {"status": "accepted"}

    return router


async def _dispatch(event: str, distinct_id: str, props: dict, org_id: str) -> None:
    """Map allowlisted event names to the typed emitter functions."""
    if event == "agent_run_completed":
        await emitter.agent_run_completed(
            org_id=org_id,
            user_id=distinct_id,
            agent_slug=props["agent_slug"],
            run_kind=props["run_kind"],
            channel=props["channel"],
            conversation_id=props.get("conversation_id"),
            schedule_name=props.get("schedule_name"),
            model=props["model"],
            input_tokens=props["input_tokens"],
            output_tokens=props["output_tokens"],
            cost_usd=props.get("cost_usd"),
            duration_ms=props["duration_ms"],
            tool_call_count=props["tool_call_count"],
            success=props["success"],
            error_type=props.get("error_type"),
        )
    elif event == "proactive_sent":
        await emitter.proactive_sent(
            org_id=org_id,
            user_id=distinct_id,
            schedule_name=props.get("schedule_name"),
            task_type=props["task_type"],
            channel=props["channel"],
            content_length=props["content_length"],
            agent_slug=props.get("agent_slug"),
            trigger=props["trigger"],
        )
    elif event == "agent_session_started":
        await emitter.agent_session_started(
            org_id=org_id,
            user_id=distinct_id,
            channel=props["channel"],
            agent_slug=props["agent_slug"],
        )
    elif event == "eval_run_completed":
        await emitter.eval_run_completed(
            dataset=props["dataset"],
            total_cases=props["total_cases"],
            passed=props["passed"],
            score=props["score"],
            prev_score=props.get("prev_score"),
            regression=props["regression"],
            duration_ms=props["duration_ms"],
        )
    elif event == "feedback_submitted":
        await emitter.feedback_submitted(
            org_id=org_id,
            user_id=distinct_id,
            agent_slug=props["agent_slug"],
            rating=props["rating"],
            has_note=props["has_note"],
            prompt_source=props["prompt_source"],
            conversation_id=props.get("conversation_id"),
        )
