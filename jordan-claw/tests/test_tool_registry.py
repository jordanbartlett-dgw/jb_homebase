from __future__ import annotations

import inspect

from jordan_claw.tools import TOOL_REGISTRY

EXPECTED_TOOLS = [
    "current_datetime",
    "search_web",
    "check_calendar",
    "schedule_event",
    "recall_memory",
    "forget_memory",
    "search_notes",
    "read_note",
    "create_source_note",
]


def test_registry_has_all_expected_tools():
    for name in EXPECTED_TOOLS:
        assert name in TOOL_REGISTRY, f"Missing tool: {name}"


def test_registry_has_no_unexpected_tools():
    assert set(TOOL_REGISTRY.keys()) == set(EXPECTED_TOOLS)


def test_registry_values_are_callable():
    for name, func in TOOL_REGISTRY.items():
        assert callable(func), f"{name} is not callable"


def test_plain_tools_have_no_ctx_param():
    """current_datetime should not accept RunContext."""
    sig = inspect.signature(TOOL_REGISTRY["current_datetime"])
    param_names = list(sig.parameters.keys())
    assert "ctx" not in param_names


def test_deps_tools_have_ctx_param():
    """Tools needing credentials should accept RunContext as first param."""
    for name in ["search_web", "check_calendar", "schedule_event", "recall_memory", "forget_memory", "search_notes", "read_note", "create_source_note"]:
        sig = inspect.signature(TOOL_REGISTRY[name])
        first_param = list(sig.parameters.keys())[0]
        assert first_param == "ctx", f"{name} first param should be 'ctx', got '{first_param}'"
