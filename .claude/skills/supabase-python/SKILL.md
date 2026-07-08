---
name: supabase-python
description: Use when working with Supabase in jb_homebase — writing queries with supabase-py, adding or applying migrations, schema changes, pgvector search, RLS, check constraints, or any "add a column/table/status" request touching the data layer.
---

# Supabase in the Claw

Data layer: hosted Supabase, async supabase-py, service key server-side.
Schema truth is `supabase/migrations/` (001–014, 005 removed). Table inventory
and column ownership: `docs/architecture.md`. Never assume a table or column —
read the migration DDL first (the `orgs` vs `organizations` bug shipped once).

## Query rules (each learned the hard way)

- **Never `maybe_single()`** — the async client returns `None` (not a result
  object) on no rows; every downstream `.data` access throws. Use
  `.limit(1).execute()` and check `result.data`.
- **Check CHECK constraints before new enum-like values.** `conversations.status`,
  `usage_events.run_kind`, `usage_events.severity` all have them. An
  unconstrained-looking `status='paused'` write broke the bot in prod once.
  Adding a value = ALTER the constraint in a migration, or design around it
  (nullable column often beats a new status — status-filtered lookups keep
  working).
- Client singleton: `db/client.py::get_supabase_client()`. Data access lives in
  `db/` table-per-module — add functions there, not inline in handlers.
- Datetimes → `.isoformat()` before insert (YAML/frontmatter `date` objects are
  not JSON-serializable — the Obsidian ingest bug).
- Connection pooling for direct Postgres: pooler port 6543 + `?pgbouncer=true`.

## Migration procedure (manual by design — no CLI runner)

1. New file `supabase/migrations/NNN_short_name.sql`, next number (015+).
2. Header comment: what it does + **deploy ordering** ("run before/after code
   deploy X") — Railway auto-deploys on merge, so ordering is load-bearing.
   Expand schema BEFORE merging code that reads it.
3. Run the SQL by hand in the Supabase **SQL Editor** on the target project.
4. After ANY schema change (new table/column):
   `SELECT pg_notify('pgrst', 'reload schema');`
   — function form only; the `NOTIFY` statement form fails in the SQL Editor.
   Skipping this 404s (`PGRST205`) or 400s ("column not found in schema cache")
   the running app.
5. Verify with a read-back query (`information_schema.columns` or a select),
   not by assuming success.
6. Idempotent SQL where possible (`IF NOT EXISTS`, guarded `array_append`) —
   these get re-run by hand.

Agents schema (current, post-014): `slug`, `system_prompt`, `model`
(provider-prefixed, e.g. `anthropic:claude-sonnet-5`), `capabilities text[]`,
`is_active`. There is NO `tools` column.

## pgvector

`obsidian_note_chunks.embedding`: 512-dim (`text-embedding-3-small`, dims set
in `obsidian/embeddings.py`). Search via RPC `search_obsidian_notes`
(`db/obsidian.py::search_notes_semantic`), always org-scoped. RLS on obsidian
tables is deny-all with no policies — anon key reads return 0 rows by design
(`tests/test_evals_isolation.py` guards this); the service key bypasses.

## Testing DB code

Mock at the client boundary (`AsyncMock`/`MagicMock`, patterns in
`tests/test_conversations.py`) — but remember mocked tests hid the
maybe_single and date-serialization bugs. Anything touching new columns or
RPCs gets one smoke test against real data before "done" (eval org
`eval-test-org` exists for safe writes; see `evals/seed_corpus.py`).
