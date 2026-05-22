"""Quick diagnostic: does Dataset.from_file load the expected number of cases?

Run inside the deployed container to compare against local behavior.
Temporary — delete once we resolve the case-count mismatch.
"""

from __future__ import annotations

import yaml
from pydantic_evals import Dataset

from evals.scorers import RequiredFactsScorer, TopKMembershipScorer
from evals.types import (
    MemoryRecallExpected,
    MemoryRecallInputs,
    ObsidianRetrievalExpected,
    ObsidianRetrievalInputs,
)

for path, inputs_t, expected_t, scorer in [
    (
        "/app/evals/datasets/memory_recall.yaml",
        MemoryRecallInputs,
        MemoryRecallExpected,
        RequiredFactsScorer,
    ),
    (
        "/app/evals/datasets/obsidian_retrieval.yaml",
        ObsidianRetrievalInputs,
        ObsidianRetrievalExpected,
        TopKMembershipScorer,
    ),
]:
    raw = yaml.safe_load(open(path))
    raw_cases = len(raw.get("cases", []))
    try:
        ds = Dataset[inputs_t, expected_t, dict].from_file(
            path, custom_evaluator_types=(scorer,)
        )
        loaded_cases = len(ds.cases)
    except Exception as e:
        loaded_cases = f"ERR: {type(e).__name__}: {e}"
    print(f"{path}: raw_yaml={raw_cases} loaded_by_pydantic_evals={loaded_cases}")
