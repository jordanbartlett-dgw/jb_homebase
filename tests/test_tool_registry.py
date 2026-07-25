from __future__ import annotations

import inspect

from jordan_claw.agents.capabilities import CAPABILITY_REGISTRY

# All tools across every capability group, keyed by registered name.
ALL_TOOLS = {
    name: tool
    for group in CAPABILITY_REGISTRY.values()
    for name, tool in group.toolset.tools.items()
}

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
    "get_workout_profile",
    "save_workout_profile",
    "get_workout_plan",
    "save_workout_plan",
    "log_workout",
    "amend_last_workout",
    "get_recent_workouts",
    "set_reminder",
    "list_reminders",
    "cancel_reminder",
    "normalize_medication",
    "fetch_fda_label",
    "get_medication_profile",
    "save_medication_profile",
    "log_health_event",
    "amend_last_health_event",
    "get_health_events",
    "get_last_visit_date",
    "create_timeline_note",
    "get_care_profile",
    "save_care_profile",
    "save_care_document",
    "check_care_docs_current",
]


def test_registry_has_all_expected_tools():
    for name in EXPECTED_TOOLS:
        assert name in ALL_TOOLS, f"Missing tool: {name}"


def test_registry_has_no_unexpected_tools():
    assert set(ALL_TOOLS.keys()) == set(EXPECTED_TOOLS)


def test_registry_values_are_callable():
    for name, tool in ALL_TOOLS.items():
        assert callable(tool.function), f"{name} is not callable"


def test_plain_tools_have_no_ctx_param():
    """current_datetime should not accept RunContext."""
    sig = inspect.signature(ALL_TOOLS["current_datetime"].function)
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
        "get_workout_profile",
        "save_workout_profile",
        "get_workout_plan",
        "save_workout_plan",
        "log_workout",
        "amend_last_workout",
        "get_recent_workouts",
        "set_reminder",
        "list_reminders",
        "cancel_reminder",
        "normalize_medication",
        "fetch_fda_label",
        "get_medication_profile",
        "save_medication_profile",
        "log_health_event",
        "amend_last_health_event",
        "get_health_events",
        "get_last_visit_date",
        "create_timeline_note",
        "get_care_profile",
        "save_care_profile",
        "save_care_document",
        "check_care_docs_current",
    ]
    for name in deps_tools:
        sig = inspect.signature(ALL_TOOLS[name].function)
        first_param = list(sig.parameters.keys())[0]
        assert first_param == "ctx", f"{name} first param should be 'ctx', got '{first_param}'"
