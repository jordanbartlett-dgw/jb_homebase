from __future__ import annotations

from jordan_claw.agents.capabilities import CAPABILITY_REGISTRY, resolve_capabilities


def test_registry_covers_all_sixteen_tools():
    tool_names = set()
    for group in CAPABILITY_REGISTRY.values():
        tool_names.update(group.toolset.tools)
    assert len(tool_names) == 16


def test_expected_groups_exist():
    assert set(CAPABILITY_REGISTRY) == {"core", "web", "calendar", "memory", "obsidian", "workout"}


def test_resolve_capabilities_maps_ids():
    groups = resolve_capabilities(["core", "workout"])
    assert [g.id for g in groups] == ["core", "workout"]


def test_resolve_capabilities_skips_unknown_with_warning():
    groups = resolve_capabilities(["core", "nonexistent"])
    assert [g.id for g in groups] == ["core"]
