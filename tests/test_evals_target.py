"""claw-eval --model: target-model override resolution and wiring.

No network. `local:` models are constructed but never called; the task-fn
wiring proof runs against TestModel.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel

from evals import target
from evals.registry import REGISTRY
from evals.run_eval import _report_key, cli
from evals.tasks.tool_routing import tool_routing_task
from evals.types import ToolRoutingInputs


@pytest.fixture(autouse=True)
def _reset_override() -> Iterator[None]:
    yield
    target.set_target_override(None)


def _settings(base_url: str = "http://127.0.0.1:8081/v1", api_key: str = "k") -> SimpleNamespace:
    return SimpleNamespace(local_llm_base_url=base_url, local_llm_api_key=api_key)


def test_target_model_returns_default_without_override() -> None:
    assert target.target_model("anthropic:claude-sonnet-5") == "anthropic:claude-sonnet-5"


def test_target_model_returns_override_when_set() -> None:
    model = TestModel()
    target.set_target_override(model)
    assert target.target_model("anthropic:claude-sonnet-5") is model


def test_build_passes_provider_prefixed_strings_through() -> None:
    assert target.build_target_model("anthropic:claude-haiku-5-5", _settings()) == (
        "anthropic:claude-haiku-5-5"
    )


def test_build_rejects_bare_model_name() -> None:
    with pytest.raises(ValueError, match="provider"):
        target.build_target_model("claude-haiku-5-5", _settings())


def test_build_local_uses_chat_completions_against_the_local_endpoint() -> None:
    model = target.build_target_model("local:Qwen3-14B-Q4_K_M", _settings())
    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "Qwen3-14B-Q4_K_M"
    assert str(model.base_url).startswith("http://127.0.0.1:8081/v1")


def test_build_local_requires_base_url() -> None:
    with pytest.raises(ValueError, match="LOCAL_LLM_BASE_URL"):
        target.build_target_model("local:Qwen3-14B-Q4_K_M", _settings(base_url=""))


async def test_task_fn_runs_on_the_override_model() -> None:
    """Wiring proof: with an override set, a real task fn never touches its
    pinned Anthropic TARGET_MODEL (which would need a key and the network)."""
    target.set_target_override(TestModel(call_tools=[], custom_output_text="from override"))
    out = await tool_routing_task(ToolRoutingInputs(user_message="hi"))
    assert out == "from override"


def test_only_the_embeddings_dataset_is_not_an_llm_target() -> None:
    assert [s.name for s in REGISTRY.values() if not s.llm_target] == ["obsidian_retrieval"]


def test_report_key_keeps_override_reports_out_of_the_baseline_glob() -> None:
    assert _report_key("tool_routing", None) == "tool_routing"
    key = _report_key("tool_routing", "local:Qwen3-14B-Q4_K_M")
    assert key == "tool_routing@local-Qwen3-14B-Q4_K_M"
    # _prune_reports / compare glob on f"{dataset}_*.json"
    assert not f"{key}_20261118T000000Z.json".startswith("tool_routing_")


def test_model_with_save_baseline_is_rejected() -> None:
    result = CliRunner().invoke(
        cli, ["run", "tool_routing", "--model", "local:x", "--save-baseline"]
    )
    assert result.exit_code == 2
    assert "--save-baseline" in result.output


def test_model_on_embeddings_only_dataset_is_rejected() -> None:
    result = CliRunner().invoke(cli, ["run", "obsidian_retrieval", "--model", "local:x"])
    assert result.exit_code == 2
    assert "no LLM target" in result.output
