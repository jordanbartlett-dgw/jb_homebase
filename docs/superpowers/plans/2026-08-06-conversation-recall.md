# Conversation Recall (`chat_history` capability) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give all three agents two tools to recall their own archived chats from the last 30 days: `search_past_conversations` (ILIKE keyword and/or date range) and `read_past_conversation` (paged transcript read).

**Architecture:** New DB helpers scope every query to org + `channel='app'` + `channel_thread_id=<agent slug>` + `status='archived'` + a server-side 30-day cap on `conversations.created_at`. New `tools/history.py` formats bounded excerpts/pages. A new `ToolGroup("chat_history")` registers both tools; `AgentDeps` gains `agent_slug` so tools know whose history to read. Grant is data migration 037.

**Tech Stack:** Python 3.12, pydantic-ai v2, supabase-py async client, pytest.

**Spec:** `docs/superpowers/specs/2026-08-06-conversation-recall-design.md`

## Global Constraints

- pydantic-ai v2 pinned; tools are plain async fns taking `ctx: RunContext[AgentDeps]` — no decorators.
- `from __future__ import annotations` in every file. Type hints always.
- Never `maybe_single()` — `.limit(1).execute()` and check `result.data`.
- `uv run` for everything; `uv run ruff check . && uv run ruff format .` before each commit.
- Run only the named test files, never the full suite.
- Conventional commits on branch `feature/conversation-recall`.
- 30-day window is enforced server-side in the tools; caller dates narrow it, never widen it.
- Both tools hard-cap output size (10 hits / 30 messages / 500-char messages) — oversized tool returns have stranded runs before (Anthropic 400).
- Docstrings are the LLM's routing signal: each states what the tool is for AND not for.

---

### Task 0: Branch

- [ ] **Step 1:** `git checkout -b feature/conversation-recall` (from up-to-date main).

---

### Task 1: `AgentDeps.agent_slug` plumbing

**Files:**
- Modify: `src/jordan_claw/agents/deps.py`
- Modify: `src/jordan_claw/gateway/router.py:94` (deps construction)
- Modify: `src/jordan_claw/proactive/executors.py:84` (deps construction)
- Modify: `src/jordan_claw/events/pipeline.py:55` (deps construction)

**Interfaces:**
- Produces: `AgentDeps.agent_slug: str = ""` — Task 3's tools read `ctx.deps.agent_slug`.

- [ ] **Step 1: Add the field**

In `agents/deps.py`, after `org_id: str` add:

```python
    agent_slug: str = ""
```

- [ ] **Step 2: Plumb all three construction sites**

Each site already has the slug in scope. Add one line to each `AgentDeps(` call:

`gateway/router.py` (~line 95, inside `handle_message`):
```python
        deps = AgentDeps(
            org_id=msg.org_id,
            agent_slug=agent_slug,
```

`proactive/executors.py` (~line 84, inside the run helper that takes `agent_slug: str`):
```python
    deps = AgentDeps(
        org_id=org_id,
        agent_slug=agent_slug,
```

`events/pipeline.py` (~line 55, inside `_run_trigger`):
```python
    deps = AgentDeps(
        org_id=trigger.org_id,
        agent_slug=trigger.agent_slug,
```

- [ ] **Step 3: Verify nothing broke**

Run: `uv run pytest tests/test_gateway.py tests/test_proactive_executors.py tests/test_event_pipeline.py tests/test_capabilities.py -q`
Expected: all pass (field is defaulted, so untouched constructions stay valid).

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check . && uv run ruff format .
git add src/jordan_claw/agents/deps.py src/jordan_claw/gateway/router.py src/jordan_claw/proactive/executors.py src/jordan_claw/events/pipeline.py
git commit -m "feat(deps): carry agent_slug on AgentDeps"
```

---

### Task 2: DB helpers

**Files:**
- Modify: `src/jordan_claw/db/conversations.py` (append two fns)
- Modify: `src/jordan_claw/db/messages.py` (append two fns)
- Create: `tests/test_db_history.py`

**Interfaces:**
- Produces (Task 3 consumes these exact signatures):
  - `search_archived_messages(client, *, org_id: str, agent_slug: str, query: str, window_start: str, window_end: str | None = None, limit: int = 10) -> list[dict]` — rows: `content, role, created_at, conversation_id`.
  - `list_recallable_conversations(client, *, org_id: str, agent_slug: str, window_start: str, window_end: str | None = None, limit: int = 10) -> list[dict]` — rows: `id, created_at`.
  - `get_recallable_conversation(client, *, conversation_id: str, org_id: str, agent_slug: str, window_start: str) -> dict | None` — row: `id, created_at`.
  - `get_conversation_messages_page(client, conversation_id: str, *, offset: int, limit: int) -> tuple[list[dict], int]` — rows `role, content, created_at` oldest-first, plus exact total count.
- Consumes: nothing new (existing `AsyncClient` patterns).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db_history.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.db.conversations import (
    get_recallable_conversation,
    list_recallable_conversations,
)
from jordan_claw.db.messages import (
    get_conversation_messages_page,
    search_archived_messages,
)

WINDOW_START = "2026-07-07T00:00:00+00:00"


def _chain(rows, count=None):
    """Mock supabase query chain: every builder method returns the chain."""
    q = MagicMock()
    for m in ("select", "eq", "gte", "lte", "in_", "ilike", "order", "limit", "range"):
        getattr(q, m).return_value = q
    q.execute = AsyncMock(return_value=MagicMock(data=rows, count=count))
    return q


def _client(q):
    db = MagicMock()
    db.table.return_value = q
    return db


@pytest.mark.asyncio
async def test_search_scopes_to_own_archived_app_thread():
    row = {
        "content": "we discussed sandbag squats",
        "role": "user",
        "created_at": "2026-08-01T10:00:00+00:00",
        "conversation_id": "c1",
    }
    q = _chain([row])
    rows = await search_archived_messages(
        _client(q),
        org_id="org-1",
        agent_slug="workout-coach",
        query="sandbag",
        window_start=WINDOW_START,
    )
    assert rows == [row]
    q.eq.assert_any_call("conversations.org_id", "org-1")
    q.eq.assert_any_call("conversations.channel", "app")
    q.eq.assert_any_call("conversations.channel_thread_id", "workout-coach")
    q.eq.assert_any_call("conversations.status", "archived")
    q.gte.assert_any_call("conversations.created_at", WINDOW_START)
    q.in_.assert_any_call("role", ["user", "assistant"])
    q.ilike.assert_any_call("content", "%sandbag%")
    q.lte.assert_not_called()


@pytest.mark.asyncio
async def test_search_applies_window_end_when_given():
    q = _chain([])
    await search_archived_messages(
        _client(q),
        org_id="org-1",
        agent_slug="claw-main",
        query="x",
        window_start=WINDOW_START,
        window_end="2026-08-02T00:00:00+00:00",
    )
    q.lte.assert_any_call("conversations.created_at", "2026-08-02T00:00:00+00:00")


@pytest.mark.asyncio
async def test_list_recallable_scopes_and_orders_newest_first():
    q = _chain([{"id": "c1", "created_at": "2026-08-01T10:00:00+00:00"}])
    rows = await list_recallable_conversations(
        _client(q),
        org_id="org-1",
        agent_slug="claw-main",
        window_start=WINDOW_START,
    )
    assert rows[0]["id"] == "c1"
    q.eq.assert_any_call("channel_thread_id", "claw-main")
    q.eq.assert_any_call("status", "archived")
    q.gte.assert_any_call("created_at", WINDOW_START)
    q.order.assert_any_call("created_at", desc=True)


@pytest.mark.asyncio
async def test_get_recallable_conversation_returns_none_when_absent():
    q = _chain([])
    row = await get_recallable_conversation(
        _client(q),
        conversation_id="nope",
        org_id="org-1",
        agent_slug="claw-main",
        window_start=WINDOW_START,
    )
    assert row is None
    q.eq.assert_any_call("id", "nope")
    q.eq.assert_any_call("status", "archived")


@pytest.mark.asyncio
async def test_messages_page_returns_rows_and_exact_total():
    q = _chain([{"role": "user", "content": "a", "created_at": "t"}], count=61)
    rows, total = await get_conversation_messages_page(
        _client(q), "c1", offset=30, limit=30
    )
    assert (len(rows), total) == (1, 61)
    q.range.assert_called_once_with(30, 59)
    q.order.assert_any_call("created_at", desc=False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db_history.py -q`
Expected: FAIL with ImportError (fns not defined).

- [ ] **Step 3: Implement the helpers**

Append to `src/jordan_claw/db/conversations.py`:

```python
async def list_recallable_conversations(
    client: AsyncClient,
    *,
    org_id: str,
    agent_slug: str,
    window_start: str,
    window_end: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Archived app-channel sessions for one agent inside the recall window."""
    query = (
        client.table("conversations")
        .select("id, created_at")
        .eq("org_id", org_id)
        .eq("channel", "app")
        .eq("channel_thread_id", agent_slug)
        .eq("status", "archived")
        .gte("created_at", window_start)
        .order("created_at", desc=True)
        .limit(limit)
    )
    if window_end is not None:
        query = query.lte("created_at", window_end)
    result = await query.execute()
    return result.data


async def get_recallable_conversation(
    client: AsyncClient,
    *,
    conversation_id: str,
    org_id: str,
    agent_slug: str,
    window_start: str,
) -> dict | None:
    """One ARCHIVED conversation, only if it belongs to this org + agent
    thread and started inside the recall window. Ownership enforcement for
    read_past_conversation lives here, in the query."""
    result = (
        await client.table("conversations")
        .select("id, created_at")
        .eq("id", conversation_id)
        .eq("org_id", org_id)
        .eq("channel", "app")
        .eq("channel_thread_id", agent_slug)
        .eq("status", "archived")
        .gte("created_at", window_start)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None
```

Append to `src/jordan_claw/db/messages.py`:

```python
async def search_archived_messages(
    client: AsyncClient,
    *,
    org_id: str,
    agent_slug: str,
    query: str,
    window_start: str,
    window_end: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """ILIKE search over one agent's archived app-channel transcripts.

    The !inner join makes the conversation filters restrict message rows;
    without it PostgREST returns messages with a null embed instead of
    filtering them out.
    """
    q = (
        client.table("messages")
        .select(
            "content, role, created_at, conversation_id, "
            "conversations!inner(org_id, channel, channel_thread_id, status, created_at)"
        )
        .eq("conversations.org_id", org_id)
        .eq("conversations.channel", "app")
        .eq("conversations.channel_thread_id", agent_slug)
        .eq("conversations.status", "archived")
        .gte("conversations.created_at", window_start)
        .in_("role", ["user", "assistant"])
        .ilike("content", f"%{query}%")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if window_end is not None:
        q = q.lte("conversations.created_at", window_end)
    result = await q.execute()
    return result.data


async def get_conversation_messages_page(
    client: AsyncClient,
    conversation_id: str,
    *,
    offset: int,
    limit: int,
) -> tuple[list[dict], int]:
    """One oldest-first page of a transcript plus the exact total row count."""
    result = (
        await client.table("messages")
        .select("role, content, created_at", count="exact")
        .eq("conversation_id", conversation_id)
        .in_("role", ["user", "assistant"])
        .order("created_at", desc=False)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data, result.count or 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db_history.py -q`
Expected: 5 passed.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check . && uv run ruff format .
git add src/jordan_claw/db/conversations.py src/jordan_claw/db/messages.py tests/test_db_history.py
git commit -m "feat(db): archived-conversation search and paged read helpers"
```

---

### Task 3: The two tools

**Files:**
- Create: `src/jordan_claw/tools/history.py`
- Create: `tests/test_history_tools.py`

**Interfaces:**
- Consumes: the four Task 2 DB helpers (exact signatures above) plus existing `get_messages_for_conversations(client, conversation_ids) -> list[dict]` from `db/messages.py`.
- Produces (Task 4 registers these): `search_past_conversations(ctx, query="", from_date="", to_date="") -> str` and `read_past_conversation(ctx, conversation_id, page=1) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history_tools.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.tools.history import (
    MESSAGE_MAX_CHARS,
    read_past_conversation,
    search_past_conversations,
)


def _ctx():
    ctx = MagicMock()
    ctx.deps.org_id = "org-1"
    ctx.deps.agent_slug = "claw-main"
    ctx.deps.supabase_client = MagicMock()
    return ctx


@pytest.mark.asyncio
async def test_search_requires_query_or_date():
    result = await search_past_conversations(_ctx())
    assert "Provide a search query" in result


@pytest.mark.asyncio
async def test_search_rejects_bad_dates():
    result = await search_past_conversations(_ctx(), query="x", from_date="last tuesday")
    assert "ISO format" in result


@pytest.mark.asyncio
async def test_search_formats_excerpts_and_points_at_read_tool():
    long_tail = "z" * 400
    rows = [
        {
            "content": f"we compared sandbag loads {long_tail}",
            "role": "user",
            "created_at": "2026-08-01T10:15:00+00:00",
            "conversation_id": "c1",
        }
    ]
    with patch(
        "jordan_claw.tools.history.search_archived_messages",
        AsyncMock(return_value=rows),
    ) as mock_search:
        result = await search_past_conversations(_ctx(), query="sandbag")
    assert "c1" in result
    assert "sandbag" in result
    assert long_tail not in result  # excerpt-bounded, never the full message
    assert "read_past_conversation" in result
    assert mock_search.call_args.kwargs["agent_slug"] == "claw-main"


@pytest.mark.asyncio
async def test_search_clamps_from_date_to_30_day_cap():
    with patch(
        "jordan_claw.tools.history.search_archived_messages",
        AsyncMock(return_value=[]),
    ) as mock_search:
        await search_past_conversations(_ctx(), query="x", from_date="2020-01-01")
    from datetime import UTC, datetime, timedelta

    window_start = datetime.fromisoformat(mock_search.call_args.kwargs["window_start"])
    assert datetime.now(UTC) - window_start <= timedelta(days=31)


@pytest.mark.asyncio
async def test_search_date_only_lists_conversations_with_openers():
    convs = [{"id": "c9", "created_at": "2026-08-04T09:00:00+00:00"}]
    msgs = [
        {"conversation_id": "c9", "role": "assistant", "created_at": "t1", "content": "hi"},
        {"conversation_id": "c9", "role": "user", "created_at": "t2", "content": "plan my week"},
    ]
    with (
        patch(
            "jordan_claw.tools.history.list_recallable_conversations",
            AsyncMock(return_value=convs),
        ),
        patch(
            "jordan_claw.tools.history.get_messages_for_conversations",
            AsyncMock(return_value=msgs),
        ),
    ):
        result = await search_past_conversations(_ctx(), from_date="2026-08-04")
    assert "c9" in result
    assert "plan my week" in result  # first USER message is the opener


@pytest.mark.asyncio
async def test_search_no_matches():
    with patch(
        "jordan_claw.tools.history.search_archived_messages",
        AsyncMock(return_value=[]),
    ):
        result = await search_past_conversations(_ctx(), query="unicorn")
    assert "No archived messages matched" in result


@pytest.mark.asyncio
async def test_read_unknown_conversation():
    with patch(
        "jordan_claw.tools.history.get_recallable_conversation",
        AsyncMock(return_value=None),
    ):
        result = await read_past_conversation(_ctx(), "nope")
    assert "No archived conversation with that id" in result


@pytest.mark.asyncio
async def test_read_pages_and_truncates_messages():
    conv = {"id": "c1", "created_at": "2026-08-01T10:00:00+00:00"}
    rows = [
        {
            "role": "assistant",
            "content": "y" * (MESSAGE_MAX_CHARS + 100),
            "created_at": "2026-08-01T10:01:00+00:00",
        }
    ]
    with (
        patch(
            "jordan_claw.tools.history.get_recallable_conversation",
            AsyncMock(return_value=conv),
        ),
        patch(
            "jordan_claw.tools.history.get_conversation_messages_page",
            AsyncMock(return_value=(rows, 61)),
        ) as mock_page,
    ):
        result = await read_past_conversation(_ctx(), "c1", page=2)
    assert "page 2 of 3" in result
    assert "61 messages" in result
    assert "y" * (MESSAGE_MAX_CHARS + 100) not in result
    assert "page=3" in result  # points at the next page
    assert mock_page.call_args.kwargs["offset"] == 30


@pytest.mark.asyncio
async def test_read_page_out_of_range():
    conv = {"id": "c1", "created_at": "2026-08-01T10:00:00+00:00"}
    with (
        patch(
            "jordan_claw.tools.history.get_recallable_conversation",
            AsyncMock(return_value=conv),
        ),
        patch(
            "jordan_claw.tools.history.get_conversation_messages_page",
            AsyncMock(return_value=([], 61)),
        ),
    ):
        result = await read_past_conversation(_ctx(), "c1", page=9)
    assert "out of range" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_history_tools.py -q`
Expected: FAIL with ModuleNotFoundError (`jordan_claw.tools.history`).

- [ ] **Step 3: Implement the tools**

Create `src/jordan_claw/tools/history.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.conversations import (
    get_recallable_conversation,
    list_recallable_conversations,
)
from jordan_claw.db.messages import (
    get_conversation_messages_page,
    get_messages_for_conversations,
    search_archived_messages,
)

RECALL_WINDOW_DAYS = 30
MAX_SEARCH_RESULTS = 10
EXCERPT_CONTEXT_CHARS = 150  # chars kept either side of a match
PAGE_SIZE = 30
MESSAGE_MAX_CHARS = 500

_EMPTY_ARGS_HINT = (
    "Provide a search query, a date range (YYYY-MM-DD), or both. "
    "Dumping all 30 days without a filter is not supported."
)


def _parse_date(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _window_bounds(from_date: str, to_date: str) -> tuple[str, str | None]:
    """ISO window bounds; the 30-day cap always wins over a wider from_date."""
    cap = datetime.now(UTC) - timedelta(days=RECALL_WINDOW_DAYS)
    start = max(_parse_date(from_date), cap) if from_date else cap
    end: str | None = None
    if to_date:
        end_dt = _parse_date(to_date)
        if len(to_date) == 10:  # bare date means that whole day, inclusive
            end_dt += timedelta(days=1)
        end = end_dt.isoformat()
    return start.isoformat(), end


def _excerpt(content: str, query: str) -> str:
    idx = content.lower().find(query.lower())
    if idx == -1:
        cut = content[: 2 * EXCERPT_CONTEXT_CHARS]
        return cut + ("..." if len(content) > len(cut) else "")
    start = max(0, idx - EXCERPT_CONTEXT_CHARS)
    end = min(len(content), idx + len(query) + EXCERPT_CONTEXT_CHARS)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(content) else ""
    return f"{prefix}{content[start:end]}{suffix}"


def _stamp(iso: str) -> str:
    return iso[:16].replace("T", " ")


async def search_past_conversations(
    ctx: RunContext[AgentDeps],
    query: str = "",
    from_date: str = "",
    to_date: str = "",
) -> str:
    """Search your own archived chats with Jordan from the last 30 days, by
    keyword and/or date range (YYYY-MM-DD). Use when Jordan refers to
    something discussed in an earlier conversation. With dates only, lists
    each conversation's opening message. NOT for durable facts about Jordan
    (use recall_memory), NOT for his notes (use search_notes), NOT for the
    web (use search_web). Follow up with read_past_conversation for full
    context."""
    if not query and not from_date and not to_date:
        return _EMPTY_ARGS_HINT
    try:
        window_start, window_end = _window_bounds(from_date, to_date)
    except ValueError:
        return "Dates must be ISO format (YYYY-MM-DD)."

    try:
        if query:
            rows = await search_archived_messages(
                ctx.deps.supabase_client,
                org_id=ctx.deps.org_id,
                agent_slug=ctx.deps.agent_slug,
                query=query,
                window_start=window_start,
                window_end=window_end,
                limit=MAX_SEARCH_RESULTS,
            )
            if not rows:
                return "No archived messages matched in the last 30 days."
            lines = [f"Found {len(rows)} matching message(s), newest first:", ""]
            for r in rows:
                lines.append(
                    f"- [{r['role']} @ {_stamp(r['created_at'])}] "
                    f"conversation {r['conversation_id']}:"
                )
                lines.append(f"  {_excerpt(r['content'], query)}")
            lines.append("")
            lines.append(
                "Use read_past_conversation(conversation_id) for full context."
            )
            return "\n".join(lines)

        convs = await list_recallable_conversations(
            ctx.deps.supabase_client,
            org_id=ctx.deps.org_id,
            agent_slug=ctx.deps.agent_slug,
            window_start=window_start,
            window_end=window_end,
            limit=MAX_SEARCH_RESULTS,
        )
        if not convs:
            return "No archived conversations in that date range."
        all_msgs = await get_messages_for_conversations(
            ctx.deps.supabase_client, [c["id"] for c in convs]
        )
        openers: dict[str, str] = {}
        for m in all_msgs:
            if m["role"] == "user" and m["conversation_id"] not in openers:
                openers[m["conversation_id"]] = m["content"]
        lines = [f"Found {len(convs)} archived conversation(s), newest first:", ""]
        for c in convs:
            opener = openers.get(c["id"], "(no user message)")
            cut = opener[: 2 * EXCERPT_CONTEXT_CHARS]
            if len(opener) > len(cut):
                cut += "..."
            lines.append(f"- {c['id']} ({_stamp(c['created_at'])}): {cut}")
        lines.append("")
        lines.append("Use read_past_conversation(conversation_id) for full context.")
        return "\n".join(lines)
    except Exception as exc:  # DB failure must not strand the run
        return f"Past-conversation search failed: {exc}"


async def read_past_conversation(
    ctx: RunContext[AgentDeps],
    conversation_id: str,
    page: int = 1,
) -> str:
    """Read one page (30 messages) of a single archived conversation
    transcript. Only use with a conversation id returned by
    search_past_conversations. NOT for the current conversation — that is
    already in your context."""
    if page < 1:
        return "page must be 1 or greater."
    window_start, _ = _window_bounds("", "")
    try:
        conversation = await get_recallable_conversation(
            ctx.deps.supabase_client,
            conversation_id=conversation_id,
            org_id=ctx.deps.org_id,
            agent_slug=ctx.deps.agent_slug,
            window_start=window_start,
        )
        if conversation is None:
            return "No archived conversation with that id in your last 30 days."
        messages, total = await get_conversation_messages_page(
            ctx.deps.supabase_client,
            conversation_id,
            offset=(page - 1) * PAGE_SIZE,
            limit=PAGE_SIZE,
        )
        pages = max(1, -(-total // PAGE_SIZE))
        if not messages:
            return f"Page {page} is out of range: this conversation has {pages} page(s)."
        lines = [
            f"Conversation {conversation_id} "
            f"(started {_stamp(conversation['created_at'])}) — "
            f"page {page} of {pages}, {total} messages:",
            "",
        ]
        for m in messages:
            content = m["content"]
            if len(content) > MESSAGE_MAX_CHARS:
                content = content[:MESSAGE_MAX_CHARS] + "..."
            lines.append(f"[{m['role']} @ {_stamp(m['created_at'])}] {content}")
        if page < pages:
            lines.append("")
            lines.append(
                f"More: read_past_conversation('{conversation_id}', page={page + 1})."
            )
        return "\n".join(lines)
    except Exception as exc:  # DB failure must not strand the run
        return f"Reading past conversation failed: {exc}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_history_tools.py -q`
Expected: 9 passed.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check . && uv run ruff format .
git add src/jordan_claw/tools/history.py tests/test_history_tools.py
git commit -m "feat(tools): search_past_conversations + read_past_conversation"
```

---

### Task 4: Registry entry, count bumps, wiring proof

**Files:**
- Modify: `src/jordan_claw/agents/capabilities.py`
- Modify: `tests/test_capabilities.py` (tool count 37→39, groups set, new wiring test)
- Modify: `tests/test_tool_registry.py` (EXPECTED_TOOLS + deps_tools lists)

**Interfaces:**
- Consumes: Task 3's two tool fns.
- Produces: `CAPABILITY_REGISTRY["chat_history"]` — the id migration 037 grants.

- [ ] **Step 1: Write the failing tests**

In `tests/test_capabilities.py`:
- Change the count assertion in `test_tool_counts_ignore_non_toolgroup_capabilities` from `== 37` to `== 39`.
- Add `"chat_history"` to the set in `test_expected_groups_exist`.
- Add after `test_email_capability_reaches_the_model`:

```python
@pytest.mark.asyncio
async def test_chat_history_capability_reaches_the_model():
    """Wiring proof: an agent granted chat_history sends both recall tool defs."""
    sent = await _sent_tools(_prod_shaped_config("claw-main", ["core", "chat_history"]))
    assert {"search_past_conversations", "read_past_conversation"} <= sent
```

In `tests/test_tool_registry.py`, append to BOTH the `EXPECTED_TOOLS` list and the `deps_tools` list inside `test_deps_tools_have_ctx_param`:

```python
    "search_past_conversations",
    "read_past_conversation",
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_capabilities.py tests/test_tool_registry.py -q`
Expected: FAIL (missing group, missing tools, count mismatch).

- [ ] **Step 3: Register the capability**

In `src/jordan_claw/agents/capabilities.py`, add the import:

```python
from jordan_claw.tools.history import read_past_conversation, search_past_conversations
```

Add to `CAPABILITY_REGISTRY` after the `"email"` entry:

```python
    "chat_history": ToolGroup(
        id="chat_history",
        description=(
            "Recall the agent's own archived chats with Jordan from the "
            "last 30 days: keyword/date search plus transcript reading."
        ),
        toolset=_toolset(
            (search_past_conversations, "search_past_conversations"),
            (read_past_conversation, "read_past_conversation"),
        ),
    ),
```

(The description is load-bearing: the classifier's agent catalog renders it, and a description-less entry has broken the catalog before.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_capabilities.py tests/test_tool_registry.py -q`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check . && uv run ruff format .
git add src/jordan_claw/agents/capabilities.py tests/test_capabilities.py tests/test_tool_registry.py
git commit -m "feat(capabilities): chat_history group with wiring proof"
```

---

### Task 5: Migration 037 + architecture doc

**Files:**
- Create: `supabase/migrations/037_chat_history_grant.sql`
- Modify: `docs/architecture.md` (capability list + tool count)

- [ ] **Step 1: Write the migration**

Create `supabase/migrations/037_chat_history_grant.sql`:

```sql
-- 037_chat_history_grant.sql
-- Grants the chat_history capability (search_past_conversations,
-- read_past_conversation) to all three agents. Own-thread archived
-- conversations only; 30-day window enforced in code.
--
-- Deploy order: data-only, apply AFTER the chat_history code deploy is
-- live (resolve_capabilities skips unknown ids, so early apply is safe
-- too). No pg_notify needed (no schema change). Idempotent.

UPDATE agents
SET capabilities = array_append(capabilities, 'chat_history')
WHERE slug IN ('claw-main', 'workout-coach', 'med-check')
  AND NOT ('chat_history' = ANY(capabilities));
```

- [ ] **Step 2: Update `docs/architecture.md`**

In the `agents/capabilities.py::CAPABILITY_REGISTRY` bullet: after the **email** group clause, add:

```
plus **chat_history** (search_past_conversations + read_past_conversation:
the agent's own archived app conversations, 30-day window, on all three
agents)
```

Change `37 distinct tools total` to `39 distinct tools total`. In the Database section, change `Migrations 001–035` to `001–037` and add `037` to the data-grants list.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/037_chat_history_grant.sql docs/architecture.md
git commit -m "feat(db): migration 037 chat_history grant + architecture map update"
```

---

### Task 6: PR, deploy, grant, prod verification

- [ ] **Step 1: Push and open the PR**

```bash
git push -u origin feature/conversation-recall
gh pr create --title "feat: conversation recall (chat_history capability)" --body "..."
```

Body summarizes the spec link, the two tools, own-thread scoping, and migration 037. End body with the standard Claude Code attribution line.

- [ ] **Step 2: Merge after CI is green** (ruff + pytest gates). Merging to main deploys.

- [ ] **Step 3: Verify the deploy** — invoke the `deploy-verify` skill: confirm the new SHA is the active Railway deploy (`railway status -s jb_homebase` etc.) and `/health` is ok. Remember `-s jb_homebase` on every railway command.

- [ ] **Step 4: Apply migration 037** via supabase-py (short literal, but consistent with how we apply grants):

```bash
infisical run --env=dev -- uv run python - <<'EOF'
import asyncio, os
from supabase._async.client import create_client

async def main():
    db = await create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    for slug in ("claw-main", "workout-coach", "med-check"):
        row = (await db.table("agents").select("capabilities").eq("slug", slug).limit(1).execute()).data[0]
        caps = row["capabilities"]
        if "chat_history" not in caps:
            await db.table("agents").update({"capabilities": [*caps, "chat_history"]}).eq("slug", slug).execute()
    readback = (await db.table("agents").select("slug, capabilities").execute()).data
    print(readback)

asyncio.run(main())
EOF
```

Expected: readback shows `chat_history` in all three agents' arrays. (The DB write is done when the row is queried back, not when the script exits.)

- [ ] **Step 5: Exercise the changed surface in prod**

Send a real message through the app (or curl `/app/messages` with `CLAW_APP_TOKEN`): "What did we talk about yesterday?" to claw-main. Confirm:
- the reply references a real prior conversation,
- the run in Logfire shows a `search_past_conversations` (and likely `read_past_conversation`) tool call,
- a `usage_events` row landed for the run.

- [ ] **Step 6: Wrap up** — update memory (`project_next_steps.md`), mark the feature shipped.
