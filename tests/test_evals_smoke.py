"""Smoke test for the eval harness wiring.

Builds a 2-case in-memory dataset, runs it against TestModel (no API call), and
asserts the dataset/evaluator/report wiring works end-to-end. Does NOT exercise
the production task_fns — those spend money and are exercised by the nightly
Railway run instead.
"""

from __future__ import annotations

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_evals import Case, Dataset

from evals.scorers import RequiredFactsScorer
from evals.types import MemoryRecallExpected, MemoryRecallInputs, MemoryState, SyntheticFact


async def _smoke_task(inputs: MemoryRecallInputs) -> str:
    agent = Agent(TestModel(custom_output_text="uv is the answer"))
    result = await agent.run(inputs.question)
    return str(result.output)


@pytest.mark.asyncio
async def test_harness_runs_end_to_end() -> None:
    cases = [
        Case(
            name="hits_required_fact",
            inputs=MemoryRecallInputs(
                memory_state=MemoryState(
                    facts=[
                        SyntheticFact(category="preference", content="Jordan uses uv")
                    ]
                ),
                question="What package manager?",
            ),
            expected_output=MemoryRecallExpected(required_facts=["uv"]),
        ),
        Case(
            name="misses_required_fact",
            inputs=MemoryRecallInputs(
                memory_state=MemoryState(),
                question="Anything?",
            ),
            expected_output=MemoryRecallExpected(required_facts=["pip"]),
        ),
    ]

    ds = Dataset[MemoryRecallInputs, MemoryRecallExpected, dict](
        name="smoke",
        cases=cases,
        evaluators=[RequiredFactsScorer()],
    )

    report = await ds.evaluate(_smoke_task, max_concurrency=2, progress=False)

    assert len(report.cases) == 2
    by_name = {c.name: c for c in report.cases}

    assert by_name["hits_required_fact"].scores["required_facts"].value == 1.0
    assert by_name["misses_required_fact"].scores["required_facts"].value == 0.0
