"""Wiring proof for the `online_eval` / `online_eval_deterministic`
capabilities (migration 034).

Registry resolution + an end-to-end run asserting the two deterministic
evaluators (MaxToolCalls, OutputSanity) fire while the groundedness LLM judge
does not, at the process-wide default sample rate of 0.0. No live API calls:
TestModel/FunctionModel only, and the judge never fires at rate 0.

`online_eval_deterministic` is the judge-free variant granted to med-check
(locked PII decision: med-check content stays out of Logfire, and the judge's
`include_input=True` plus its own instrumented agent would export it if
sampled). Its own test below walks the evaluator list and asserts no
`LLMJudge` instance is present at all, so raising the process-wide judge
sample rate can never make med-check judge-sampled by accident.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import fields

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_evals.evaluators import EvaluationResult, EvaluatorFailure, LLMJudge
from pydantic_evals.online import DEFAULT_CONFIG, CallbackSink, configure, wait_for_evaluations
from pydantic_evals.online_capability import OnlineEvaluation

from jordan_claw.agents.capabilities import CAPABILITY_REGISTRY, ToolGroup
from jordan_claw.agents.online_evaluators import GROUNDEDNESS_JUDGE, OutputSanity


def test_online_eval_registry_entry_resolves():
    cap = CAPABILITY_REGISTRY["online_eval"]
    assert isinstance(cap, OnlineEvaluation)
    assert cap.id == "online_eval"
    assert not isinstance(cap, ToolGroup)


def test_online_eval_deterministic_registry_entry_resolves():
    cap = CAPABILITY_REGISTRY["online_eval_deterministic"]
    assert isinstance(cap, OnlineEvaluation)
    assert cap.id == "online_eval_deterministic"
    assert not isinstance(cap, ToolGroup)


def test_online_eval_deterministic_has_no_judge():
    """The judge-free variant must never carry an LLMJudge evaluator, in any
    form (bare or wrapped), regardless of future edits to the registry."""
    cap = CAPABILITY_REGISTRY["online_eval_deterministic"]
    assert isinstance(cap, OnlineEvaluation)
    for online_evaluator in cap.evaluators:
        evaluator = online_evaluator.evaluator
        assert not isinstance(evaluator, LLMJudge)


def test_online_eval_is_excluded_from_toolgroup_counts():
    """Non-ToolGroup capabilities are already skipped by both count tests;
    this just proves online_eval falls into that bucket (no regression)."""
    tool_names: set[str] = set()
    for group in CAPABILITY_REGISTRY.values():
        if isinstance(group, ToolGroup):
            tool_names.update(group.toolset.tools)
    assert "online_eval" not in tool_names
    assert "online_eval_deterministic" not in tool_names


@pytest.fixture
def restore_online_eval_config():
    """`configure()` mutates the process-wide `DEFAULT_CONFIG` in place.

    Snapshot every field and restore it after the test so this test can't
    leak sample-rate/sink changes into other tests (or prod code paths)
    that share the same global.
    """
    snapshot = {f.name: getattr(DEFAULT_CONFIG, f.name) for f in fields(DEFAULT_CONFIG)}
    try:
        yield
    finally:
        for name, value in snapshot.items():
            setattr(DEFAULT_CONFIG, name, value)


@pytest.mark.asyncio
async def test_deterministic_evaluators_fire_judge_does_not_at_zero_rate(
    restore_online_eval_config,
):
    received: list[Sequence[EvaluationResult]] = []

    def sink(
        results: Sequence[EvaluationResult],
        failures: Sequence[EvaluatorFailure],
        ctx,
    ) -> None:
        received.append(results)

    # Mirrors prod defaults: online eval on, judge-sampled rate at 0 until
    # explicitly enabled. emit_otel_events=False keeps this test from also
    # asserting on OTel span export, which isn't the mechanism under test.
    configure(default_sink=CallbackSink(sink), default_sample_rate=0.0, emit_otel_events=False)

    agent = Agent(
        "test",
        name="probe",
        capabilities=[CAPABILITY_REGISTRY["online_eval"]],
    )

    def plain_text(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content="hello there")])

    await agent.run("hi", model=FunctionModel(plain_text))
    await wait_for_evaluations()

    names = {result.name for batch in received for result in batch}
    assert "MaxToolCalls" in names
    assert "OutputSanity" in names
    assert "groundedness" not in names


def test_output_sanity_evaluator_shape():
    """Unit-level check on the deterministic evaluator's own logic, independent
    of the online-eval dispatch machinery exercised above."""
    from pydantic_evals.evaluators import EvaluatorContext
    from pydantic_evals.otel._errors import SpanTreeRecordingError

    def _ctx(output: object) -> EvaluatorContext:
        return EvaluatorContext(
            name=None,
            inputs="hi",
            output=output,
            expected_output=None,
            metadata=None,
            duration=0.0,
            _span_tree=SpanTreeRecordingError("no spans in this unit test"),
            attributes={},
            metrics={},
        )

    evaluator = OutputSanity()
    assert evaluator.evaluate(_ctx("a fine reply")) is True
    assert evaluator.evaluate(_ctx("")) is False
    assert evaluator.evaluate(_ctx("x" * 20_000)) is False
    assert evaluator.evaluate(_ctx(None)) is False


def test_groundedness_judge_shape():
    assert GROUNDEDNESS_JUDGE.model is None
    assert GROUNDEDNESS_JUDGE.include_input is True
    assert GROUNDEDNESS_JUDGE.assertion is False
    assert GROUNDEDNESS_JUDGE.score == {"evaluation_name": "groundedness", "include_reason": True}
