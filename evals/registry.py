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

from evals.scorers import PhraseAssertionScorer, RequiredFactsScorer, TopKMembershipScorer
from evals.tasks.med_check import TARGET_MODEL as MED_CHECK_TARGET_MODEL
from evals.tasks.med_check import med_check_task
from evals.tasks.memory_recall import TARGET_MODEL as MEMORY_RECALL_TARGET_MODEL
from evals.tasks.memory_recall import memory_recall_task
from evals.tasks.obsidian_retrieval import obsidian_retrieval_task
from evals.types import (
    MedCheckExpected,
    MedCheckInputs,
    MemoryRecallExpected,
    MemoryRecallInputs,
    ObsidianRetrievalExpected,
    ObsidianRetrievalInputs,
    RetrievalOutput,
)
from jordan_claw.obsidian.embeddings import EMBEDDING_MODEL as OBSIDIAN_EMBEDDING_MODEL

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
    target_model: str


REGISTRY: dict[str, EvalSpec] = {
    "memory_recall": EvalSpec(
        name="memory_recall",
        yaml_path=DATASETS_DIR / "memory_recall.yaml",
        task_fn=memory_recall_task,
        inputs_type=MemoryRecallInputs,
        expected_type=MemoryRecallExpected,
        output_type=str,
        custom_evaluators=(RequiredFactsScorer,),
        target_model=MEMORY_RECALL_TARGET_MODEL,
    ),
    "obsidian_retrieval": EvalSpec(
        name="obsidian_retrieval",
        yaml_path=DATASETS_DIR / "obsidian_retrieval.yaml",
        task_fn=obsidian_retrieval_task,
        inputs_type=ObsidianRetrievalInputs,
        expected_type=ObsidianRetrievalExpected,
        output_type=RetrievalOutput,
        custom_evaluators=(TopKMembershipScorer,),
        # No LLM call — embeddings-only retrieval.
        target_model=f"openai:{OBSIDIAN_EMBEDDING_MODEL}",
    ),
    "med_check": EvalSpec(
        name="med_check",
        yaml_path=DATASETS_DIR / "med_check.yaml",
        task_fn=med_check_task,
        inputs_type=MedCheckInputs,
        expected_type=MedCheckExpected,
        output_type=str,
        custom_evaluators=(PhraseAssertionScorer,),
        target_model=MED_CHECK_TARGET_MODEL,
    ),
}
