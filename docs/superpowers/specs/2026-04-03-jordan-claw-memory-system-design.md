# Jordan Claw Memory System Design

**Date:** 2026-04-03
**Author:** Jordan Bartlett
**Status:** Draft
**Scope:** Memory system only. Obsidian integration and proactive messaging are separate specs.

---

## Context

Jordan Claw operates statelessly. Each conversation starts from zero. Preferences, decisions, and patterns must be restated every session. This is the first of three specs (Memory, Obsidian Integration, Proactive Messaging) that give Claw persistent context.

The memory system accumulates facts, decisions, and preferences per tenant. It injects a compact summary into every agent request and provides a tool for deeper queries. Memory is extracted automatically from conversations via a background task.

## Decisions

These were resolved during brainstorming:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Extraction timing | Async (background task) | Zero added latency to user response |
| Background worker | asyncio.create_task() in FastAPI | No queue infra needed at current volume |
| Data model | All three tables (facts, events, context) | Full PRD schema from the start |
| Conflict handling | Auto-replace low confidence (<0.7), flag high confidence | Balances automation with safety |
| Read path | Hybrid: summary in system prompt + recall_memory tool | Ambient awareness + deep queries without burning tokens |
| Extraction method | Second LLM call (Haiku) with structured output | Clean separation, independently tunable |

---

## Data Model

### `memory_facts`

Persistent declarative knowledge about the tenant or their world.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK, gen_random_uuid() |
| org_id | uuid | FK organizations(id), NOT NULL |
| category | text | NOT NULL. One of: `preference`, `decision`, `entity`, `workflow`, `relationship` |
| content | text | NOT NULL. The fact in natural language |
| source | text | NOT NULL. One of: `conversation`, `explicit`, `inferred` |
| confidence | float | NOT NULL, default 0.8. Range 0.0-1.0 |
| metadata | jsonb | Default '{}'. Tags, conversation_id, needs_review flag |
| created_at | timestamptz | Default now() |
| updated_at | timestamptz | Default now() |
| expires_at | timestamptz | Nullable. For time-bound facts |
| is_archived | boolean | Default false. Decayed or superseded facts |

**Indexes:**
- `idx_memory_facts_org_active(org_id) WHERE is_archived = false` -- read path
- `idx_memory_facts_org_category(org_id, category) WHERE is_archived = false` -- filtered queries

**RLS:** Enable RLS. Service role bypasses. Future: policy on `org_id = auth.uid()`.

### `memory_events`

Timestamped log of significant interactions. Append-only.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK, gen_random_uuid() |
| org_id | uuid | FK organizations(id), NOT NULL |
| event_type | text | NOT NULL. One of: `decision`, `task_completed`, `feedback`, `milestone`, `correction` |
| summary | text | NOT NULL. What happened |
| context | jsonb | Default '{}'. Related entities, conversation_id |
| created_at | timestamptz | Default now() |

**Indexes:**
- `idx_memory_events_org_created(org_id, created_at DESC)` -- recent events query

**RLS:** Same as memory_facts.

### `memory_context`

Pre-rendered prompt blocks ready for injection.

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK, gen_random_uuid() |
| org_id | uuid | FK organizations(id), NOT NULL |
| scope | text | NOT NULL. `global` for now. Future: `project:claw`, `vertical:sales` |
| context_block | text | NOT NULL. Rendered markdown for system prompt |
| is_stale | boolean | Default true |
| last_computed | timestamptz | Nullable |

**Constraints:** UNIQUE(org_id, scope).

**RLS:** Same as memory_facts.

### Migration

File: `supabase/migrations/002_memory_tables.sql`

---

## Write Path (Memory Extraction)

### Flow

```
User message
    → agent.run()
    → response sent to user immediately
    → asyncio.create_task(extract_memory_background(...))
        → load existing facts for org
        → extraction_agent.run() with structured output
        → upsert facts (with conflict resolution)
        → append events
        → mark memory_context as stale
```

### Extraction Agent

A dedicated Pydantic AI agent using `claude-haiku-4-5-20251001` with structured result type.

**Input context:**
- The user message
- The assistant response
- All active (non-archived) facts for this org, each serialized with its `id`, `category`, `content`, and `confidence` (so the extraction agent can reference `replaces_fact_id`)

**Output models:**

```python
class ExtractedFact(BaseModel):
    content: str
    category: Literal["preference", "decision", "entity", "workflow", "relationship"]
    source: Literal["conversation", "explicit", "inferred"]
    confidence: float  # 0.0-1.0
    replaces_fact_id: str | None  # Set if this contradicts an existing fact

class ExtractedEvent(BaseModel):
    event_type: Literal["decision", "task_completed", "feedback", "milestone"]
    summary: str

class ExtractionResult(BaseModel):
    facts: list[ExtractedFact]
    events: list[ExtractedEvent]
    has_corrections: bool  # True if user explicitly corrected something
```

### Extraction Prompt

The system prompt instructs the extraction agent to:
1. Identify new facts, updated facts, and notable events from this conversation turn
2. Set `replaces_fact_id` if a fact contradicts or updates an existing one
3. Skip facts already captured in the existing facts list
4. Set `source='explicit'` and `confidence=1.0` when the user explicitly says "remember that..."
5. Set `has_corrections=true` when the user corrects a previous statement
6. Be conservative: only extract facts with clear signal, not every passing mention

### Conflict Resolution

When `replaces_fact_id` is set:
- If existing fact confidence < 0.7: update the existing row with new content/confidence
- If existing fact confidence >= 0.7: insert the new fact with `metadata.needs_review = true`, keep the old fact active
- If `has_corrections` is true: archive the old fact, insert new with `confidence=1.0`, append a `correction` event

### Dedup

Handled by the extraction agent itself. The full existing facts list is included in the prompt. The agent is instructed to only output genuinely new or updated information.

At current scale (~50-200 facts per tenant), passing all facts to Haiku is feasible. When fact count grows past ~500, switch to passing only facts in the relevant categories.

### Integration Point

In `gateway/router.py`, after Step 6 (save assistant message):

```python
asyncio.create_task(
    extract_memory_background(db, msg.org_id, msg.content, response_text)
)
```

Fire-and-forget. Errors logged but don't affect the user response.

---

## Read Path (Context Injection + Tool)

### System Prompt Injection

Before agent.run() in handle_message():

1. Query `memory_context` for `(org_id, scope='global')`
2. If `is_stale=true` or no row exists:
   a. Load all active facts for org, ordered by confidence DESC, updated_at DESC
   b. Load last 20 events for org
   c. Render into a markdown context block (see format below)
   d. Upsert into memory_context with `is_stale=false`
3. Prepend the context block to the agent's system prompt

### Context Block Format

```markdown
## Memory Context

### Preferences
- Prefers concise, direct communication
- Uses Pydantic AI + FastAPI stack (not n8n)

### Decisions
- [Apr 1] Chose watchfiles over Git sync for Obsidian pipeline
- [Mar 28] Prioritized memory system over scheduled reports

### Entities
- DGW: promotional products social enterprise
- Foster Greatness: nonprofit for foster youth

### Recent Activity
- [Apr 2] Completed Phase 2 tool registry implementation
- [Apr 1] Decided on DB-driven agent config architecture
```

### Token Budget

Cap the context block at ~500 tokens. If facts exceed this:
1. Include all facts with confidence >= 0.9 (explicit/pinned)
2. Fill remaining budget with highest confidence, most recently updated
3. Truncate least confident/oldest facts

### `recall_memory` Tool

Registered in `TOOL_REGISTRY` and added to the agent's tools array in the DB.

```python
async def recall_memory(
    ctx: RunContext[AgentDeps],
    query: str,
    category: str | None = None,
) -> str:
    """Search memory for specific facts. Use when asked 'what do you know about...'
    or when you need deeper context than what's in your memory summary."""
```

**Search implementation:** ILIKE on `content` column with optional `category` filter. Returns up to 20 matching facts formatted as bullet points. Vector search deferred to future spec.

### Explicit Commands

The main agent's system prompt includes instructions to:
- **"Remember that..."** → Respond confirming, then extraction agent processes with `source='explicit'`, `confidence=1.0`
- **"Forget..."** → Call a `forget_memory` tool that searches facts by keyword (ILIKE on content) and archives all matches. If multiple matches, the agent confirms with the user before archiving.
- **"What do you know about me/X?"** → Call `recall_memory` tool

Tools needed: `recall_memory` and `forget_memory` (both in the registry).

---

## New Files

```
jordan-claw/src/jordan_claw/
├── memory/
│   ├── __init__.py
│   ├── models.py          # ExtractionResult, ExtractedFact, ExtractedEvent
│   ├── extractor.py       # Extraction agent, prompt, background task
│   └── reader.py          # Context loading, recomputation, rendering
├── db/
│   └── memory.py          # CRUD: get_active_facts, upsert_facts, append_events,
│                          #        get_memory_context, mark_context_stale, search_facts,
│                          #        archive_fact
├── tools/
│   └── memory.py          # recall_memory, forget_memory tool implementations
└── supabase/migrations/
    └── 002_memory_tables.sql
```

## Modified Files

| File | Change |
|------|--------|
| `gateway/router.py` | Add memory context loading before agent build (read path). Add asyncio.create_task for extraction after response (write path). |
| `agents/factory.py` | Accept optional `memory_context` param, prepend to system prompt. |
| `agents/deps.py` | Add `supabase_client` field to AgentDeps so memory tools can query DB. |
| `tools/__init__.py` | Add `recall_memory` and `forget_memory` to TOOL_REGISTRY. |
| `config.py` | Add `anthropic_api_key` already exists. No new env vars needed (extraction agent uses same key). |

## DB Agent Config Update

Add `recall_memory` and `forget_memory` to the `tools` array for the `claw-main` agent in the `agents` table.

---

## Memory Maintenance

### Confidence Decay

A nightly task (Railway cron job or asyncio scheduled task) that:
1. Queries facts where `updated_at < now() - interval '30 days'` and `confidence > 0.3` and `is_archived = false`
2. Sets `confidence = confidence - 0.1`
3. Archives facts where confidence drops below 0.3 (sets `is_archived = true`)

This is a single SQL UPDATE + a conditional UPDATE, no LLM call.

### When to Build Decay

Decay is low priority for initial launch. Memory will accumulate for weeks before decay matters. Build it after the core read/write paths are working.

---

## Verification Plan

### Unit Tests
- Extraction agent returns valid ExtractionResult for sample conversation turns
- Conflict resolution: auto-replace low confidence, flag high confidence
- Context rendering: facts grouped by category, token budget respected
- recall_memory returns matching facts
- forget_memory archives the correct fact

### Integration Tests
- Full loop: send message via gateway, verify facts extracted and stored in DB
- Memory context injected into subsequent agent requests
- Stale flag cleared after recomputation, set after new extraction

### Manual Smoke Test
1. Send a message to @jb_homebase_bot: "I prefer working in the morning"
2. Wait 5 seconds for extraction
3. Query `memory_facts` in Supabase: verify the preference fact exists
4. Send another message: "What do you know about me?"
5. Verify the agent uses recall_memory and surfaces the preference
6. Send: "Actually, I prefer working at night"
7. Verify the old fact is updated/archived and the new one exists with appropriate confidence

---

## Out of Scope

- Vector/semantic search on memory facts (future, likely with Obsidian spec)
- Memory editing UI (CLI/API only)
- Cross-tenant memory sharing
- Obsidian note ingestion (separate spec)
- Proactive messaging (separate spec)
- Memory summary proactive behavior (deferred to proactive messaging spec)
