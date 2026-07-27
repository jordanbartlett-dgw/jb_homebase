from __future__ import annotations

from typing import Annotated

import structlog
from logfire.experimental.annotations import record_feedback
from pydantic import BaseModel, Field, StrictBool, StrictFloat, StrictInt

from jordan_claw.config import Settings

log = structlog.get_logger()

TRACEPARENT_PATTERN = r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"
NAME_PATTERN = r"^[a-z_]{1,32}$"


class FeedbackRecordError(Exception):
    """Logfire rejected the feedback; the route maps this to a 502.

    Message is client-safe; provider details are logged server-side instead.
    """


class FeedbackRequest(BaseModel):
    """User feedback attached to a completed agent run's trace.

    `value` accepts bool | int | float | str because Logfire renders each
    differently (numbers -> scores, strings -> labels, bools -> assertions).
    Strict member types plus smart union matching keep `True` from being
    silently coerced into `1`.
    """

    traceparent: str = Field(pattern=TRACEPARENT_PATTERN)
    name: str = Field(pattern=NAME_PATTERN)
    value: StrictBool | StrictInt | StrictFloat | Annotated[str, Field(max_length=200)]
    comment: str | None = Field(default=None, max_length=2000)


async def record_app_feedback(settings: Settings, body: FeedbackRequest) -> None:
    """Attach feedback to the run's trace via Logfire.

    Takes `settings` to match the other app-route handlers' signature; the
    route already confirmed `settings.logfire_token` is set before calling
    this (returns 503 otherwise), so it is not read here. Any failure
    becomes a `FeedbackRecordError`; the route maps that to a 502.
    """
    try:
        record_feedback(body.traceparent, body.name, body.value, comment=body.comment)
    except Exception as exc:
        log.warning("feedback_record_failed", name=body.name, error=str(exc))
        raise FeedbackRecordError("Failed to record feedback") from exc
