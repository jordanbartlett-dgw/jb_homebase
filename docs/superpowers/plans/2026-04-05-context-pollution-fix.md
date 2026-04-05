# Context Pollution Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix context pollution that causes Jordan Claw to lose intent on multi-turn conversations by adding tool-routing signals and token-budgeted history.

**Architecture:** Update tool docstrings with explicit internal/external routing boundaries. Add a character-based token budget to `db_messages_to_history()` that drops oldest messages first. Update the agent's system prompt in Supabase with a routing taxonomy.

**Tech Stack:** Python, Pydantic AI, Supabase (SQL update), pytest

**Spec:** `docs/superpowers/specs/2026-04-05-context-pollution-fix-design.md`

---

### Task 1: Update tool docstrings for routing

**Files:**
- Modify: `jordan-claw/src/jordan_claw/tools/obsidian.py:20-28` (`search_notes` docstring)
- Modify: `jordan-claw/src/jordan_claw/tools/obsidian.py:58-63` (`read_note` docstring)
- Modify: `jordan-claw/src/jordan_claw/tools/web_search.py:9-14` (`search_web` docstring)

- [ ] **Step 1: Update `search_notes` docstring**

In `jordan-claw/src/jordan_claw/tools/obsidian.py`, replace the `search_notes` docstring:

```python
async def search_notes(
    ctx: RunContext[AgentDeps],
    query: str,
    note_type: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Search Jordan's personal Obsidian notes and saved research.
    Only use when Jordan asks about his own notes, past research, or previously saved content.
    Do NOT use this to discover new people, companies, content, or external information.
    Use read_note to get the full content of a specific result."""
```

- [ ] **Step 2: Update `read_note` docstring**

In the same file, replace the `read_note` docstring:

```python
async def read_note(
    ctx: RunContext[AgentDeps],
    title: str,
) -> str:
    """Read the full content of an Obsidian note by title.
    Only use after search_notes returns a relevant result.
    Returns the complete note body, tags, and linked notes."""
```

- [ ] **Step 3: Update `search_web` docstring**

In `jordan-claw/src/jordan_claw/tools/web_search.py`, replace the `search_web` docstring:

```python
async def search_web(ctx: RunContext[AgentDeps], query: str) -> str:
    """Search the web for information from the outside world.
    Use for discovering new people, companies, content creators, products,
    recommendations, current events, comparisons, or anything not already
    in Jordan's notes or memory. Default to this tool when unsure whether
    information is in Jordan's notes or on the web."""
```

- [ ] **Step 4: Commit**

```bash
git add jordan-claw/src/jordan_claw/tools/obsidian.py jordan-claw/src/jordan_claw/tools/web_search.py
git commit -m "fix: add explicit routing signals to tool docstrings

search_notes now scoped to personal notes only.
search_web now default for external discovery."
```

---

### Task 2: Add token-budgeted history

**Files:**
- Modify: `jordan-claw/src/jordan_claw/agents/factory.py:47-63`
- Test: `jordan-claw/tests/test_agents.py`

- [ ] **Step 1: Write failing test for budget truncation**

Add to `jordan-claw/tests/test_agents.py`:

```python
def test_history_budget_truncates_oldest_messages():
    """When messages exceed token budget, oldest are dropped."""
    db_rows = [
        {"role": "user", "content": "A" * 4000},      # ~1000 tokens
        {"role": "assistant", "content": "B" * 4000},  # ~1000 tokens
        {"role": "user", "content": "C" * 4000},       # ~1000 tokens
        {"role": "assistant", "content": "D" * 4000},  # ~1000 tokens
        {"role": "user", "content": "E" * 400},        # ~100 tokens
        {"role": "assistant", "content": "F" * 400},   # ~100 tokens
    ]
    # Budget of 2200 tokens (~8800 chars) should keep the last 2 exchanges
    result = db_messages_to_history(db_rows, max_tokens=2200)

    assert len(result) == 4  # messages 3-6 kept
    assert isinstance(result[0], ModelRequest)
    assert result[0].parts[0].content == "C" * 4000
    assert isinstance(result[-1], ModelResponse)
    assert result[-1].parts[0].content == "F" * 400
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd jordan-claw && python -m pytest tests/test_agents.py::test_history_budget_truncates_oldest_messages -v
```

Expected: FAIL — `db_messages_to_history()` does not accept `max_tokens` parameter.

- [ ] **Step 3: Write failing test for minimum preservation**

Add to `jordan-claw/tests/test_agents.py`:

```python
def test_history_budget_preserves_most_recent_exchange():
    """Even with a tiny budget, the most recent user+assistant pair is kept."""
    db_rows = [
        {"role": "user", "content": "A" * 40000},      # ~10000 tokens, way over budget
        {"role": "assistant", "content": "B" * 40000},  # ~10000 tokens
    ]
    result = db_messages_to_history(db_rows, max_tokens=100)

    # Must keep at least the most recent exchange regardless of budget
    assert len(result) == 2
    assert isinstance(result[0], ModelRequest)
    assert isinstance(result[1], ModelResponse)
```

- [ ] **Step 4: Run test to verify it fails**

```bash
cd jordan-claw && python -m pytest tests/test_agents.py::test_history_budget_preserves_most_recent_exchange -v
```

Expected: FAIL — same reason.

- [ ] **Step 5: Write failing test for no-budget backward compatibility**

Add to `jordan-claw/tests/test_agents.py`:

```python
def test_history_no_budget_returns_all():
    """When max_tokens is 0 (disabled), all messages are returned."""
    db_rows = [
        {"role": "user", "content": "A" * 40000},
        {"role": "assistant", "content": "B" * 40000},
        {"role": "user", "content": "C" * 40000},
        {"role": "assistant", "content": "D" * 40000},
    ]
    result = db_messages_to_history(db_rows, max_tokens=0)
    assert len(result) == 4
```

- [ ] **Step 6: Run test to verify it fails**

```bash
cd jordan-claw && python -m pytest tests/test_agents.py::test_history_no_budget_returns_all -v
```

Expected: FAIL — same reason.

- [ ] **Step 7: Implement token-budgeted history**

Replace `db_messages_to_history` in `jordan-claw/src/jordan_claw/agents/factory.py`:

```python
CHARS_PER_TOKEN = 4


def db_messages_to_history(
    messages: list[dict],
    max_tokens: int = 4000,
) -> list[ModelRequest | ModelResponse]:
    """Convert DB message rows to Pydantic AI message history format.

    Only converts user and assistant messages. Skips system and tool roles.
    When max_tokens > 0, drops oldest messages first to stay within budget.
    Always preserves at least the most recent user+assistant exchange.
    """
    # First pass: filter to user/assistant and convert
    converted: list[tuple[ModelRequest | ModelResponse, int]] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        char_count = len(content)

        if role == "user":
            converted.append((ModelRequest(parts=[UserPromptPart(content=content)]), char_count))
        elif role == "assistant":
            converted.append((ModelResponse(parts=[TextPart(content=content)]), char_count))

    if not converted or max_tokens <= 0:
        return [item for item, _ in converted]

    # Second pass: walk newest-to-oldest, accumulate within budget
    max_chars = max_tokens * CHARS_PER_TOKEN
    kept: list[ModelRequest | ModelResponse] = []
    total_chars = 0
    for i in range(len(converted) - 1, -1, -1):
        item, char_count = converted[i]
        if total_chars + char_count > max_chars and len(kept) >= 2:
            break
        kept.append(item)
        total_chars += char_count

    kept.reverse()
    return kept
```

- [ ] **Step 8: Run all three new tests**

```bash
cd jordan-claw && python -m pytest tests/test_agents.py::test_history_budget_truncates_oldest_messages tests/test_agents.py::test_history_budget_preserves_most_recent_exchange tests/test_agents.py::test_history_no_budget_returns_all -v
```

Expected: All PASS.

- [ ] **Step 9: Run existing history tests to check backward compatibility**

```bash
cd jordan-claw && python -m pytest tests/test_agents.py -v
```

Expected: All PASS. Existing tests (`test_empty_history`, `test_user_and_assistant_messages`, `test_system_and_tool_roles_skipped`) pass because their messages are small and fit within the 4000-token default.

- [ ] **Step 10: Commit**

```bash
git add jordan-claw/src/jordan_claw/agents/factory.py jordan-claw/tests/test_agents.py
git commit -m "fix: add token budget to conversation history

Drops oldest messages when history exceeds 4000 tokens (~16k chars).
Always preserves the most recent user+assistant exchange."
```

---

### Task 3: Update agent system prompt in Supabase

**Files:**
- None (SQL update against live DB)

- [ ] **Step 1: Run SQL update**

Execute against Supabase (via the dashboard SQL editor or `psql`):

```sql
UPDATE agents
SET system_prompt = E'## Tool Routing\nYour tools are either *internal* (notes, memory, calendar — Jordan''s own data) or *external* (web search — the outside world). Use internal tools only when Jordan asks about his own notes, saved content, or schedule. For discovering new people, companies, trends, recommendations, or any new information, use search_web. When in doubt, default to search_web.\n\n' || system_prompt
WHERE slug = 'jordan-assistant'
  AND system_prompt NOT LIKE '%Tool Routing%';
```

The `NOT LIKE` guard prevents double-prepending if run twice.

- [ ] **Step 2: Verify the update**

```sql
SELECT LEFT(system_prompt, 300) FROM agents WHERE slug = 'jordan-assistant';
```

Expected: Output starts with `## Tool Routing`.

---

### Task 4: Manual smoke test

- [ ] **Step 1: Deploy**

Push to main (Railway auto-deploys).

- [ ] **Step 2: Test external discovery routing**

Send via Telegram: "Find content creators similar to Dan Koe in the personal development and AI space"

Expected: Agent calls `search_web`, returns external results. Does NOT call `search_notes`.

- [ ] **Step 3: Test internal note retrieval**

Send via Telegram: "What do my notes say about personal development?"

Expected: Agent calls `search_notes`, returns Obsidian results.

- [ ] **Step 4: Test multi-turn coherence**

Have a 5+ turn conversation mixing topics. Verify the agent doesn't repeat itself or produce incoherent responses.
