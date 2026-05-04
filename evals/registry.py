"""Eval dataset registry.

Each entry binds a YAML dataset to its task fn, type schema, and any custom
evaluator types that aren't built into pydantic-evals.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic_evals.evaluators import Evaluator

from evals.scorers import RequiredFactsScorer, TopKMembershipScorer
from evals.tasks.memory_recall import memory_recall_task
from evals.tasks.obsidian_retrieval import obsidian_retrieval_task
from evals.types import (
    MemoryRecallExpected,
    MemoryRecallInputs,
    ObsidianRetrievalExpected,
    ObsidianRetrievalInputs,
    RetrievalOutput,
)

DATASETS_DIR = Path(__file__).parent / "datasets"
BASELINES_DIR = Path(__file__).parent / "baselines"
REPORTS_DIR = Path(__file__).parent / "reports"


@dataclass(frozen=True)
class EvalSpec:
    name: str
    yaml_path: Path
    task_fn: Callable[[Any], Awaitable[Any]]
    inputs_type: type
    expected_type: type
    output_type: type
    custom_evaluators: tuple[type[Evaluator], ...]


REGISTRY: dict[str, EvalSpec] = {
    "memory_recall": EvalSpec(
        name="memory_recall",
        yaml_path=DATASETS_DIR / "memory_recall.yaml",
        task_fn=memory_recall_task,
        inputs_type=MemoryRecallInputs,
        expected_type=MemoryRecallExpected,
        output_type=str,
        custom_evaluators=(RequiredFactsScorer,),
    ),
    "obsidian_retrieval": EvalSpec(
        name="obsidian_retrieval",
        yaml_path=DATASETS_DIR / "obsidian_retrieval.yaml",
        task_fn=obsidian_retrieval_task,
        inputs_type=ObsidianRetrievalInputs,
        expected_type=ObsidianRetrievalExpected,
        output_type=RetrievalOutput,
        custom_evaluators=(TopKMembershipScorer,),
    ),
}
