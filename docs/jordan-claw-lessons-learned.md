# Jordan Claw: Lessons Learned

Every bug, every wrong assumption, every "why isn't this working" moment from building Jordan Claw across Phases 1 through 3 and the fixes that followed. Written so the next session (or the next project) doesn't hit the same walls.

---

## 1. The Table That Wasn't Called "orgs"

**What happened**: Code and migrations referenced a table called `orgs`. The actual table in `001_initial_schema.sql` is `organizations`. Runtime failures across queries and new migrations.

**Why it happened**: Assumed the short name. Nobody checked the schema file before writing new code against it.

**How to avoid it**: Before writing any migration or DB query, open the schema file and verify the table name. Short names feel natural but they're assumptions until you've read the DDL.

**The fix**: Find-and-replace `orgs` to `organizations` across all affected files. Committed as a standalone fix.

---

## 2. supabase-py's `maybe_single()` Returns None, Not an Empty Result

**What happened**: Used `maybe_single().execute()` expecting it to return a result object with `.data = None`. It returns `None` itself. Every downstream `.data` access threw `AttributeError: 'NoneType' object has no attribute 'data'`. Crashed dedup checks and conversation lookups during the Phase 1 smoke test.

**Why it happened**: The supabase-py async client doesn't behave like the JS client. The Python docs don't make this obvious.

**How to avoid it**: Never use `maybe_single()`. Use `.limit(1).execute()` instead. Always returns a result object with `.data` as a list. Check `len(result.data) > 0` for existence.

**The fix**: Replaced all `maybe_single()` calls with `.limit(1)` pattern.

---

## 3. PostgREST Doesn't See New Tables Until You Reload the Schema Cache

**What happened**: Ran `CREATE TABLE` in the Supabase SQL Editor. Tables existed in `pg_tables`. PostgREST returned 404 with `PGRST205: Could not find the table in the schema cache` on every query.

**Why it happened**: PostgREST caches the database schema at startup. DDL changes don't trigger a reload. The `NOTIFY pgrst, 'reload schema'` command didn't work from the SQL Editor due to a transaction commit issue.

**How to avoid it**: After any migration that creates or alters tables, run `SELECT pg_notify('pgrst', 'reload schema');` in the SQL Editor. The function form works reliably. If that doesn't work, restart the project from the Supabase Dashboard.

**The fix**: Ran `SELECT pg_notify('pgrst', 'reload schema');` and added this step to the migration checklist.

---

## 4. Pydantic AI Validates API Keys at Agent Construction Time

**What happened**: Unit tests that constructed `Agent("anthropic:claude-sonnet-4-20250514", ...)` failed because Pydantic AI validates the Anthropic API key when the agent object is created. No key in the test environment means instant failure.

**Why it happened**: The test plan assumed agent construction was lazy. It's not. Model validation is eager.

**How to avoid it**: Always use `model="test"` in test configs. The `"test"` model skips all credential validation. Also, inspect registered tools via `agent._function_toolset.tools` (a dict keyed by tool name), not `_function_tools` which doesn't exist.

**The fix**: Updated all test fixtures to use `model="test"` and corrected tool inspection to `_function_toolset.tools`.

---

## 5. Subagent Review Rounds Can Drift Function Signatures

**What happened**: During calendar integration, a code review subagent changed `get_calendar_events` from accepting `str` to `datetime` for its date parameters. The Pydantic AI tool wrapper in `factory.py` still passed strings. The create path worked (it had `str | datetime` handling), but the read path crashed in production.

**Why it happened**: The subagent fixed the implementation but didn't update the call site. Unit tests mocked at the boundary between the tool wrapper and the calendar function, so the type mismatch was invisible.

**How to avoid it**: After any review round that changes function signatures, verify all call sites match. Run an integration-level check, not just unit tests that mock the boundary. The mock hides the exact thing that breaks.

**The fix**: Updated the tool wrapper to pass the correct types. Added a note to verify call sites after every signature change.

---

## 6. python-frontmatter Parses YAML Dates as datetime.date Objects

**What happened**: During the first live Obsidian vault ingest, Supabase inserts failed because frontmatter date fields like `captured: 2025-03-15` were parsed as `datetime.date` objects. These aren't JSON-serializable.

**Why it happened**: The `python-frontmatter` library silently parses YAML date strings into Python date objects. Unit tests used synthetic data (plain strings), so the serialization issue never surfaced.

**How to avoid it**: When working with YAML/frontmatter parsing, always sanitize the output dict before passing to Supabase. Convert any `datetime.date` or `datetime.datetime` values to ISO strings. Smoke test with real data, not just synthetic fixtures.

**The fix**: Added a sanitization step that converts date objects to `.isoformat()` strings before insert.

---

## 7. hatch Build Packages Must Include Non-src Directories for CLI Entry Points

**What happened**: The `obsidian-sync` CLI entry point was defined in `pyproject.toml` pointing to `scripts.obsidian_sync.cli:cli`. Running it failed with `ModuleNotFoundError` because hatch only packaged `src/jordan_claw`.

**Why it happened**: The `[tool.hatch.build.targets.wheel] packages` list only included the main source directory. The `scripts/` directory wasn't listed, so it wasn't included in the wheel.

**How to avoid it**: When adding CLI entry points from directories outside `src/`, verify the hatch build config includes them. Check `pyproject.toml` before declaring the CLI works.

**The fix**: Added `scripts` to the hatch packages list.

---

## 8. Tool Docstrings Are the LLM's Primary Routing Signal

**What happened**: The agent used `search_notes` (Obsidian knowledge base) instead of `search_web` (Tavily) when asked to "find content creators similar to Dan Koe." It returned summaries of personal notes instead of searching the web. When corrected, it asked for topics again, then summarized notes again. Eventually it returned a weather summary.

**Why it happened**: The `search_notes` docstring said "Search Jordan's Obsidian knowledge base by concept or keyword." That's broad enough to match any query. The `search_web` docstring said "recent events, facts, or anything that benefits from up-to-date data," which doesn't obviously match "find people." The LLM had no clear signal about which tool to use for external discovery vs. internal retrieval.

**How to avoid it**: Pydantic AI sends tool docstrings to the LLM as tool descriptions. These are the primary routing signal. Every tool docstring should explicitly state what it's for AND what it's not for. Add a general routing taxonomy to the system prompt: internal tools (notes, memory, calendar) vs. external tools (web search). Make the default explicit: "When in doubt, use search_web."

**The fix**: Updated `search_notes` to say "Do NOT use this to discover new people, companies, content, or external information." Updated `search_web` to say "Default to this tool when unsure." Added a tool-routing block to the system prompt via migration `005_agent_tool_routing_prompt.sql`.

---

## 9. Unbounded Conversation History Causes Context Saturation

**What happened**: After several tool-heavy turns, the agent lost the ability to track user intent. By turn 7, it was returning incoherent responses (a weather summary when asked about content creators). The context window was full of prior tool results replayed as conversation history.

**Why it happened**: `get_recent_messages()` loaded up to 50 messages with no token budget. Assistant responses that included tool output (Obsidian note content, web search results) were saved verbatim and replayed in full on every subsequent turn. After a few turns, the noise overwhelmed the signal.

**How to avoid it**: Always enforce a token budget on conversation history. Walk messages newest-to-oldest and stop when the budget is exhausted. Keep the budget well below the model's context window to leave room for the system prompt, memory context, and tool results.

**The fix**: Added `max_tokens=4000` parameter to `db_messages_to_history()`. Walks newest-to-oldest, drops oldest messages first. Always preserves at least the most recent user+assistant exchange. Also added a guard against orphan `ModelResponse` messages at the head of history (which happens when the current user message is the last in the DB and the budget is tight).

---

## 10. Single Conversation Per Channel Causes Cross-Topic Bleed

**What happened**: After deploying the token budget and routing fixes, the agent still couldn't resolve "these topics" from the previous turn. It referenced "weather/forecasting topics" and "the Karpathy article we just saved," things from conversations days earlier. When the user reconfirmed the topics, the agent asked what they wanted to do with them instead of searching.

**Why it happened**: `get_or_create_conversation` matched on `org_id + channel + channel_thread_id`. For Telegram DMs, the thread ID is the user's chat ID, which never changes. Every message Jordan ever sent went into a single conversation. The "last 50 messages" (now token-budgeted to ~4000 tokens) included exchanges from completely different topics and sessions.

**How to avoid it**: Conversations need session boundaries. A conversation should represent a coherent interaction, not an infinite thread. After some idle period, close the old conversation and start a new one.

**The fix**: Added a 30-minute session timeout to `get_or_create_conversation`. When the last message in a conversation is older than 30 minutes, it closes the conversation (sets `status = 'closed'`) and creates a new one. No migration needed because the `conversations` table already had a `status` column.

---

## Patterns Across These Failures

Three patterns show up repeatedly:

1. **Unit tests with mocks hide integration failures.** The mock draws a line at exactly the wrong place. The supabase-py `maybe_single` bug, the calendar type drift, the YAML date serialization issue. All invisible to unit tests because the mock sits at the boundary where the real behavior diverges. Smoke test with real data before declaring done.

2. **Defaults that made sense for one user become problems at scale.** One conversation per channel. 50 messages of history. Broad tool docstrings. All reasonable when there's one user sending five messages a day. All broken when usage patterns get more complex. Design defaults with expiry in mind.

3. **The LLM reads what you give it, not what you meant.** Tool docstrings, system prompts, and conversation history are the LLM's entire world. If the docstring says "by concept or keyword," the LLM will use the tool for any concept or keyword. If the history contains weather discussions, the LLM might talk about weather. Be explicit about boundaries. Make the default action obvious. The LLM can't infer intent from silence.
