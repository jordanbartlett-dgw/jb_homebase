"""Target-model override for `claw-eval run --model`.

Each dataset pins its own TARGET_MODEL. The override swaps that model for one
run so the same cases can score a candidate (a local llama.cpp model, a
cheaper hosted model) without editing task files. The judge is not affected.
"""

from __future__ import annotations

from typing import Protocol

from pydantic_ai.models import Model

LOCAL_PREFIX = "local:"

_override: Model | str | None = None
_local = False


class _LocalLLMSettings(Protocol):
    local_llm_base_url: str
    local_llm_api_key: str


def set_target_override(model: Model | str | None, *, local: bool = False) -> None:
    global _override, _local
    _override = model
    _local = local and model is not None


def is_local_target() -> bool:
    """True when the override is a `local:` model. Tasks use it to add
    instructions that small open-weight models need and Claude does not."""
    return _local


def target_model(default: str) -> Model | str:
    """The model a task fn should run on: the override if set, else its pin."""
    return _override if _override is not None else default


def build_target_model(spec: str, settings: _LocalLLMSettings) -> Model | str:
    """Resolve a --model value.

    `local:<name>` builds a chat-completions model against LOCAL_LLM_BASE_URL.
    It gets its own provider on purpose: pointing OPENAI_BASE_URL at llama.cpp
    would also redirect the embeddings client, which reads that env var.
    Anything else must be a pydantic-ai `provider:model` string.
    """
    if spec.startswith(LOCAL_PREFIX):
        if not settings.local_llm_base_url:
            raise ValueError("LOCAL_LLM_BASE_URL is not set; required for local: models.")
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(
            spec.removeprefix(LOCAL_PREFIX),
            provider=OpenAIProvider(
                base_url=settings.local_llm_base_url,
                api_key=settings.local_llm_api_key or "unused",
            ),
        )
    if ":" not in spec:
        raise ValueError(
            f"'{spec}' needs a provider prefix, e.g. anthropic:<model> or local:<model>."
        )
    return spec
