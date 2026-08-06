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
            lines.append("Use read_past_conversation(conversation_id) for full context.")
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
            lines.append(f"More: read_past_conversation('{conversation_id}', page={page + 1}).")
        return "\n".join(lines)
    except Exception as exc:  # DB failure must not strand the run
        return f"Reading past conversation failed: {exc}"
