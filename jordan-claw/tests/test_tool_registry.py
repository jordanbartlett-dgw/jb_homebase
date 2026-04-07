from __future__ import annotations

import inspect

from jordan_claw.tools import BASE_TOOLSET

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
    "fetch_article",
]


def test_registry_has_all_expected_tools():
    for name in EXPECTED_TOOLS:
        assert name in BASE_TOOLSET.tools, f"Missing tool: {name}"


def test_registry_has_no_unexpected_tools():
    assert set(BASE_TOOLSET.tools.keys()) == set(EXPECTED_TOOLS)


def test_registry_values_are_callable():
    for name, tool in BASE_TOOLSET.tools.items():
        assert callable(tool.function), f"{name} is not callable"


def test_plain_tools_have_no_ctx_param():
    """current_datetime should not accept RunContext."""
    sig = inspect.signature(BASE_TOOLSET.tools["current_datetime"].function)
    param_names = list(sig.parameters.keys())
    assert "ctx" not in param_names


def test_deps_tools_have_ctx_param():
    """Tools needing credentials should accept RunContext as first param."""
    deps_tools = [
        "search_web",
        "check_calendar",
        "schedule_event",
        "recall_memory",
        "forget_memory",
        "search_notes",
        "read_note",
        "create_source_note",
        "fetch_article",
    ]
    for name in deps_tools:
        sig = inspect.signature(BASE_TOOLSET.tools[name].function)
        first_param = list(sig.parameters.keys())[0]
        assert first_param == "ctx", f"{name} first param should be 'ctx', got '{first_param}'"
