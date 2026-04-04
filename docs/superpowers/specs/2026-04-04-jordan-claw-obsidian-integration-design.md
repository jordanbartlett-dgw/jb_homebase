# Jordan Claw Obsidian Integration Design

**Date:** 2026-04-04
**Author:** Jordan Bartlett
**Status:** Draft
**Scope:** Obsidian vault ingestion, search tools, and source note creation. Proactive messaging is a separate spec.

---

## Context

Jordan Claw has a memory system that extracts facts from conversations, but no access to Jordan's Obsidian knowledge base (~279 markdown files on the MINISFORUM). The vault contains atomic notes, source notes, stories, ADRs, and project docs built over months of deliberate knowledge work.

This spec gives Claw read access to the vault's knowledge and the ability to create new source notes. Claw runs on Railway, the vault lives on the MINISFORUM, so Supabase bridges the gap. A local sync script handles both directions on a scheduled cadence.

## Decisions

Resolved during brainstorming:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Storage bridge | Supabase (not local API/MCP/git) | Fits existing stack, works with Railway, gives pgvector for free |
| Sync cadence | Scheduled (twice weekly), not live | ~208 files change at human speed. Live watching is overkill. |
| Write scope | Source notes only (v1) | Jordan has a separate process for creating atomic notes from sources |
| Search approach | Semantic (pgvector) + keyword/tag filters | Semantic for conceptual queries, keyword for precise lookups |
| Embedding model | OpenAI text-embedding-3-small, 512 dimensions | Cheap, good quality, native 512-dim support |
| Chunking | Threshold-based (>1000 tokens), 10% overlap | Most notes are short enough for a single embedding |
| Note storage | Dedicated `obsidian_notes` table (not `memory_facts`) | Notes are rich documents, not single-line facts |
| Wiki-link graph | jsonb array on note row (not separate table) | Light touch. Promote to join table later if graph queries needed |
| Ingestion targets | `30-Notes/`, `20-Sources/`, `15-Stories/` | ~208 files. Primary knowledge base + narrative content |

---

## Data Model

### `obsidian_notes`

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK, gen_random_uuid() |
| org_id | uuid | FK organizations(id), NOT NULL |
| vault_path | text | NOT NULL. Relative path, e.g. `30-Notes/From Operator to Owner.md` |
| title | text | NOT NULL. Extracted from filename or frontmatter |
| note_type | text | NOT NULL. `atomic-note`, `source`, `story`, `adr` |
| content | text | NOT NULL. Full markdown body (excluding frontmatter) |
| frontmatter | jsonb | NOT NULL. Raw parsed frontmatter |
| tags | text[] | Extracted from frontmatter tags array |
| wiki_links | text[] | Extracted `[[Note Name]]` references |
| source_origin | text | NOT NULL. `vault` (ingested from disk) or `claw` (created by agent) |
| sync_status | text | NOT NULL. `synced`, `pending_export` (claw-created, not yet on disk) |
| content_hash | text | NOT NULL. SHA-256 of raw file content, for change detection during sync |
| created_at | timestamptz | Default now() |
| is_archived | boolean | Default false. Set true when vault file deleted during sync |
| updated_at | timestamptz | Default now() |

**Constraints:** UNIQUE(org_id, vault_path)

**Indexes:**
- `idx_obsidian_notes_org_type(org_id, note_type) WHERE is_archived = false` -- filtered queries
- `idx_obsidian_notes_tags` -- GIN index on tags array

**RLS:** Enable RLS. Service role bypasses. Future: policy on `org_id = auth.uid()`.

### `obsidian_note_chunks`

| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK, gen_random_uuid() |
| note_id | uuid | FK obsidian_notes(id) ON DELETE CASCADE |
| chunk_index | int | 0-based position within the note |
| content | text | NOT NULL. Chunk text |
| embedding | vector(512) | OpenAI text-embedding-3-small |
| token_count | int | NOT NULL |
| created_at | timestamptz | Default now() |

**Indexes:**
- `idx_obsidian_note_chunks_note_id(note_id)` -- chunk lookup by parent
- `idx_obsidian_note_chunks_embedding` -- HNSW index on embedding column

**RLS:** Same as obsidian_notes.

### Chunking Logic

- Notes under ~1000 tokens: single chunk, embed the whole note
- Notes over ~1000 tokens: split at markdown heading boundaries or paragraph breaks, 10% overlap between adjacent chunks
- Each chunk links back to the parent note via `note_id`

### Migration

File: `supabase/migrations/003_obsidian_tables.sql`

Enables pgvector extension if not already enabled. Creates both tables, indexes, and RLS policies. After running, execute `SELECT pg_notify('pgrst', 'reload schema')` for PostgREST cache.

---

## Claw Tools

Three tools added to `TOOL_REGISTRY`.

### `search_notes`

```python
async def search_notes(
    ctx: RunContext[AgentDeps],
    query: str,
    note_type: str | None = None,
    tags: list[str] | None = None,
) -> str:
```

**Behavior:**
1. If `tags` provided, filter `obsidian_notes` by tag overlap (ANY match)
2. If `note_type` provided, filter by note_type
3. Generate embedding for `query` via OpenAI API
4. Cosine similarity search on `obsidian_note_chunks`, joined back to `obsidian_notes` for metadata
5. Return top 10 results: title, note_type, tags, relevance score, and a snippet (matching chunk content, truncated to ~200 tokens)

The agent sees enough context to decide which note to read in full.

### `read_note`

```python
async def read_note(
    ctx: RunContext[AgentDeps],
    title: str,
) -> str:
```

**Behavior:**
1. Lookup by title (case-insensitive ILIKE match)
2. Return full content, frontmatter summary, tags, and wiki_links
3. If multiple matches, return a list of titles for the agent to disambiguate

### `create_source_note`

```python
async def create_source_note(
    ctx: RunContext[AgentDeps],
    title: str,
    url: str,
    author: str,
    source_type: str,
    tags: list[str],
    summary: str,
    key_takeaways: list[str],
) -> str:
```

**Behavior:**
1. Render markdown in the `20-Sources/` format:
   - Frontmatter: type, title, url, author, source-type, captured (today's date), tags, status (`processed`)
   - Body: Summary section, Key Takeaways section, Related Topics section (empty), Notes section (empty)
2. Insert into `obsidian_notes` with `source_origin='claw'`, `sync_status='pending_export'`
3. Generate embedding, insert chunk(s) into `obsidian_note_chunks`
4. Set `vault_path` to `20-Sources/{title}.md`
5. Return confirmation with the note title

The tool handles formatting to match vault conventions. The agent provides structured data, not raw markdown.

---

## Sync Script

A local Python CLI that runs on the MINISFORUM. Located at `jordan-claw/scripts/obsidian_sync/`.

### `obsidian-sync ingest`

Vault to Supabase direction.

1. Walk `30-Notes/`, `20-Sources/`, `15-Stories/`
2. For each `.md` file:
   a. Parse frontmatter via `python-frontmatter` library
   b. Compute SHA-256 of raw file content
   c. Extract wiki-links via regex (`\[\[([^\]]+)\]\]`)
   d. Check if `vault_path` exists in `obsidian_notes`
   e. If new: insert note, chunk content, generate embeddings, insert chunks
   f. If exists but hash changed: update note row, delete old chunks, regenerate chunks + embeddings
   g. If exists and hash matches: skip
3. Detect deletions: notes in DB with `source_origin='vault'` whose `vault_path` no longer exists on disk. Set `is_archived` or soft-delete flag (not hard delete).
4. Log summary: X inserted, Y updated, Z skipped, W archived

### `obsidian-sync export`

Supabase to vault direction.

1. Query `obsidian_notes` where `sync_status='pending_export'`
2. For each note:
   a. Render markdown file (frontmatter + body sections)
   b. Write to vault path on disk (e.g. `/home/jb/Documents/Obsidian Vault/20-Sources/Article - Title.md`)
   c. Compute content_hash of the written file
   d. Update DB: `sync_status='synced'`, update `content_hash`
3. Log summary: X notes exported

### `obsidian-sync run`

Convenience command that runs `ingest` then `export` in sequence.

### Scheduling

Cron job on the MINISFORUM, twice weekly (Wednesday and Sunday at 3am):

```
0 3 * * 0,3 cd /path/to/jb_homebase && uv run obsidian-sync run >> /var/log/obsidian-sync.log 2>&1
```

### Script Structure

```
jordan-claw/scripts/obsidian_sync/
├── __init__.py
├── cli.py               # CLI entry point (click or argparse)
├── ingest.py            # vault -> supabase
├── export.py            # supabase -> vault
├── parser.py            # frontmatter + wiki-link extraction
└── embeddings.py        # chunking + OpenAI embedding calls
```

Uses the same Supabase credentials as Claw (pulled from Infisical or `.env`).

---

## Integration Points

### AgentDeps

Add `openai_api_key: str` to `AgentDeps` for embedding generation in `search_notes` at runtime.

### Tool Registry

Add three entries to `TOOL_REGISTRY` in `tools/__init__.py`:

```python
"search_notes": search_notes,
"read_note": read_note,
"create_source_note": create_source_note,
```

### DB Agent Config

Add `search_notes`, `read_note`, `create_source_note` to the `tools` array for the `claw-main` agent in the `agents` table.

### System Prompt Addition

Add to the agent's system prompt:

> You have access to Jordan's Obsidian knowledge base. Use `search_notes` when asked about concepts, ideas, or sources. Use `read_note` to get the full content of a specific note. Use `create_source_note` when Jordan shares or you find a valuable article, resource, or reference worth capturing.

### New Files

```
jordan-claw/src/jordan_claw/
├── tools/
│   └── obsidian.py          # search_notes, read_note, create_source_note
├── db/
│   └── obsidian.py          # CRUD: search_notes_semantic, get_note_by_title,
│                            #        insert_note, get_pending_exports
jordan-claw/scripts/
└── obsidian_sync/
    ├── __init__.py
    ├── cli.py               # CLI entry point
    ├── ingest.py            # vault -> supabase
    ├── export.py            # supabase -> vault
    ├── parser.py            # frontmatter + wiki-link extraction
    └── embeddings.py        # chunking + OpenAI embedding calls
```

### Modified Files

| File | Change |
|------|--------|
| `tools/__init__.py` | Add three obsidian tools to TOOL_REGISTRY |
| `agents/deps.py` | Add `openai_api_key` to AgentDeps |
| `config.py` | Add `openai_api_key` to Settings |

### Migration

File: `supabase/migrations/003_obsidian_tables.sql`

---

## Verification Plan

### Unit Tests

- **Parser:** Frontmatter extraction, wiki-link regex, content hash generation for sample notes from each folder
- **Chunking:** Notes under 1000 tokens produce single chunk. Notes over 1000 tokens split at headings with 10% overlap. Chunk count and token counts are correct.
- **`create_source_note`:** Renders correct markdown format matching `20-Sources/` conventions
- **`search_notes`:** Returns results filtered by note_type and tags. Semantic results ranked by similarity.
- **`read_note`:** Returns full content for exact match. Returns disambiguation list for multiple matches.

### Integration Tests

- **Ingest:** Run ingest against a test vault directory with 3-4 sample notes. Verify notes and chunks land in Supabase. Run again with no changes, verify all skipped. Modify one file, verify only that note re-ingested.
- **Export:** Insert a `pending_export` note in DB. Run export. Verify file written to correct vault path with correct frontmatter format. Verify `sync_status` flipped to `synced`.
- **Deletion detection:** Remove a file from test vault, run ingest, verify DB note archived.

### Manual Smoke Test

1. Run `obsidian-sync ingest` on the real vault. Verify ~208 notes in `obsidian_notes`, chunks + embeddings in `obsidian_note_chunks`.
2. Message Claw: "What notes do I have about psychological safety?"
3. Verify `search_notes` returns relevant results from `30-Notes/` and `20-Sources/`.
4. Message Claw: "Read the full note on Mindfulness to Psychological Safety Chain"
5. Verify `read_note` returns the complete note content.
6. Message Claw: "Save this as a source note: [share a URL and summary]"
7. Verify note appears in `obsidian_notes` with `sync_status='pending_export'`.
8. Run `obsidian-sync export`. Verify file appears in `20-Sources/` on disk.

---

## Out of Scope

- Live file watching / real-time sync
- Writing atomic notes from Claw (Jordan has a separate process)
- Full wiki-link graph traversal (links stored as array, not a join table)
- Vector search on memory_facts (separate concern)
- Obsidian plugin development
- Cross-tenant vault sharing
- Proactive messaging based on vault content (separate spec)
