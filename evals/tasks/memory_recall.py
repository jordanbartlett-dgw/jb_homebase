"""Memory-recall task: synthesize a memory context block from a synthetic state,
run a stripped-down agent with it, return the string output.

Deviation from plan: the original spec said monkeypatch `db.memory.get_active_facts`
and run the real claw-main agent. That requires a DB-backed `claw-main` agent
config row in the eva org and a live Supabase connection — overkill, since the
eval question is "given memory context X, can the model answer Y." Memory recall
behavior is independent of tool wiring, so we render the state via the same
`render_context_block` helper the gateway uses, then run a tools-free agent
against it. Faithful test of the same prompt path; far simpler.
"""

from __future__ import annotations

from pydantic_ai import Agent

from evals.types import MemoryRecallInputs
from jordan_claw.config import get_settings
from jordan_claw.memory.models import MemoryFact
from jordan_claw.memory.reader import render_context_block

# claw-main's production model. Hardcoded here rather than loaded from DB
# because eval runs are independent of agent-config-table state.
TARGET_MODEL = "anthropic:claude-sonnet-4-5-20250929"

SYSTEM_SUFFIX = (
    "You are Jordan's personal AI assistant. Use the memory context above to "
    "answer questions accurately. When the question references something in "
    "memory, ground your response in the recorded facts rather than guessing."
)


def _state_to_facts(state) -> list[MemoryFact]:
    """Adapt synthetic facts to the MemoryFact shape render_context_block expects."""
    return [
        MemoryFact(
            id=f"synthetic-{i}",
            org_id=get_settings().eval_test_org_id,
            category=f.category,
            content=f.content,
            source="conversation",
            confidence=f.confidence,
            metadata={},
            created_at="2026-05-01T00:00:00Z",
            updated_at="2026-05-01T00:00:00Z",
        )
        for i, f in enumerate(state.facts)
    ]


def _state_to_events(state) -> list[dict]:
    return [
        {"summary": e.summary, "created_at": e.created_at}
        for e in state.events
    ]


async def memory_recall_task(inputs: MemoryRecallInputs) -> str:
    facts = _state_to_facts(inputs.memory_state)
    events = _state_to_events(inputs.memory_state)
    memory_block = render_context_block(facts, events)

    instructions = f"{memory_block}\n\n{SYSTEM_SUFFIX}" if memory_block else SYSTEM_SUFFIX

    agent = Agent(TARGET_MODEL, instructions=instructions)
    result = await agent.run(inputs.question)
    return str(result.output)
