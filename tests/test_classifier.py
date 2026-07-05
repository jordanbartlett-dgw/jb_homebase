from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from jordan_claw.gateway.classifier import (
    CONFIDENCE_FLOOR,
    DEFAULT_AGENT,
    RouteDecision,
    classify,
)

ORG_ID = "org-1"

AGENT_ROWS = [
    {
        "slug": "claw-main",
        "name": "Claw Main",
        "capabilities": ["core", "web", "calendar", "memory", "obsidian"],
    },
    {
        "slug": "workout-coach",
        "name": "Workout Coach",
        "capabilities": ["core", "calendar", "memory", "workout"],
    },
]


def _mock_db(rows: list[dict]) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.data = rows

    chain = MagicMock()
    chain.execute = AsyncMock(return_value=result)
    chain.select.return_value = chain
    chain.eq.return_value = chain
    db.table.return_value = chain
    return db


def _test_classifier(agent_slug: str, confidence: float) -> Agent:
    """Classifier agent backed by TestModel emitting a fixed RouteDecision."""
    return Agent(
        TestModel(custom_output_args={"agent_slug": agent_slug, "confidence": confidence}),
        output_type=RouteDecision,
    )


# --- RouteDecision contract ---


def test_route_decision_is_frozen_and_bounded():
    decision = RouteDecision(agent_slug="claw-main", confidence=0.8)
    with pytest.raises(ValidationError):
        decision.agent_slug = "other"
    with pytest.raises(ValidationError):
        RouteDecision(agent_slug="claw-main", confidence=1.2)
    with pytest.raises(ValidationError):
        RouteDecision(agent_slug="claw-main", confidence=-0.1)


# --- routing ---


async def test_workout_transcript_routes_to_workout_coach():
    db = _mock_db(AGENT_ROWS)
    with patch(
        "jordan_claw.gateway.classifier.build_classifier",
        return_value=_test_classifier("workout-coach", 0.92),
    ) as mock_build:
        slug = await classify(db, "log my bench press, three sets of five at 185", ORG_ID)

    assert slug == "workout-coach"
    # Catalog is built from agents table slugs + capability descriptions
    catalog = mock_build.call_args.args[0]
    assert "workout-coach" in catalog
    assert "claw-main" in catalog
    assert "workout logging" in catalog  # description from CAPABILITY_REGISTRY


async def test_generic_transcript_routes_to_claw_main():
    db = _mock_db(AGENT_ROWS)
    with patch(
        "jordan_claw.gateway.classifier.build_classifier",
        return_value=_test_classifier("claw-main", 0.9),
    ):
        slug = await classify(db, "what's on my calendar tomorrow", ORG_ID)

    assert slug == "claw-main"


# --- threshold ---


async def test_low_confidence_falls_back_to_default():
    db = _mock_db(AGENT_ROWS)
    with patch(
        "jordan_claw.gateway.classifier.build_classifier",
        return_value=_test_classifier("workout-coach", 0.4),
    ):
        slug = await classify(db, "hmm maybe something", ORG_ID)

    assert slug == DEFAULT_AGENT


async def test_confidence_at_floor_is_accepted():
    db = _mock_db(AGENT_ROWS)
    with patch(
        "jordan_claw.gateway.classifier.build_classifier",
        return_value=_test_classifier("workout-coach", CONFIDENCE_FLOOR),
    ):
        slug = await classify(db, "did my long run this morning", ORG_ID)

    assert slug == "workout-coach"


# --- unknown slug ---


async def test_unknown_slug_falls_back_to_default():
    db = _mock_db(AGENT_ROWS)
    with patch(
        "jordan_claw.gateway.classifier.build_classifier",
        return_value=_test_classifier("email-triage", 0.95),
    ):
        slug = await classify(db, "check my email", ORG_ID)

    assert slug == DEFAULT_AGENT


async def test_empty_catalog_falls_back_to_default():
    db = _mock_db([])
    with patch(
        "jordan_claw.gateway.classifier.build_classifier",
        return_value=_test_classifier("workout-coach", 0.99),
    ):
        slug = await classify(db, "log my workout", ORG_ID)

    assert slug == DEFAULT_AGENT


# --- failure fallback ---


async def test_classifier_failure_falls_back_to_default():
    db = _mock_db(AGENT_ROWS)
    with patch(
        "jordan_claw.gateway.classifier.build_classifier",
        side_effect=RuntimeError("model exploded"),
    ):
        slug = await classify(db, "anything at all", ORG_ID)

    assert slug == DEFAULT_AGENT


async def test_db_failure_falls_back_to_default():
    db = MagicMock()
    db.table.side_effect = RuntimeError("db down")

    slug = await classify(db, "anything at all", ORG_ID)

    assert slug == DEFAULT_AGENT
