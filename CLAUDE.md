# jb_homebase — Jordan Claw agent platform

Multi-channel AI agent gateway: FastAPI + pydantic-ai v2 + Supabase, two Telegram
bots (long-polling) + a Flutter iOS app, deployed on Railway. One process runs
everything: web routes, both bots, and the proactive scheduler.

**Read `docs/architecture.md` before planning any change.** It is the maintained
system map (message flows, module index with file:line, env vars, DB tables,
idempotency patterns). Do not re-derive the architecture by walking the tree.

## Layout

- `src/jordan_claw/` — the Python package (repo root, NOT a `jordan-claw/` subdir)
- `flutter_app/` — JB Homebase iOS app (thin client over the gateway)
- `supabase/migrations/` — hand-numbered SQL, applied manually (see below)
- `evals/` — pydantic-evals harness (`claw-eval`), nightly on Railway cron
- `scripts/obsidian_sync/` — vault ingest/export CLI
- `docs/` — see the trust map at the bottom; some docs are historical snapshots

## Invariants (violating these has shipped bugs before)

- **pydantic-ai v2 only** (pinned `>=2.0.0,<3`): `Agent(model, instructions=...,
  capabilities=[...], deps_type=AgentDeps)`; `result.output` (never `.data`);
  `result.usage` is an attribute (never `.usage()`); fields are
  `input_tokens`/`output_tokens` (never `request_tokens`/`response_tokens`).
- **Agents are DB rows** (`agents` table): `system_prompt`, `model`, and
  `capabilities text[]` live in the DB, not code. The `tools` column is GONE
  (migration 014). Model names are provider-prefixed: `anthropic:claude-sonnet-5`.
  Granting a tool = appending its capability id to the array (data migration).
- **Never `maybe_single()`** — supabase-py returns `None`, not a result object.
  Use `.limit(1).execute()` and check `result.data`.
- **Check CHECK constraints before writing a new enum-like value.** The
  conversations `status` constraint broke prod once already. Read the actual
  DDL in `supabase/migrations/` first; the table is `organizations`, not `orgs`.
- **Migrations are manual**: next number (015+), run by hand in the Supabase SQL
  Editor, header comment states deploy-order. After any schema change PostgREST
  needs `SELECT pg_notify('pgrst', 'reload schema');` (the function form —
  `NOTIFY` fails in the SQL Editor). Expand schema BEFORE merging code that
  reads it; Railway deploys the instant main moves.
- **Conversations rotate**: 30-min idle archives the conversation and mints a
  fresh one (`db/conversations.py`). Any per-conversation state you add must
  survive or intentionally reset across that rotation — reason about it explicitly.
- **Never run the gateway locally with prod tokens.** Telegram allows one
  `getUpdates` consumer per token; a local run steals polling from prod (409).
  Local dev: use stub tokens or the local-stub pattern in
  `flutter_app/integration_test/live_chat_test.dart`.

## Discipline

- **Tool docstrings are the LLM's routing signal.** Every agent tool docstring
  states what the tool is for AND what it is not for (e.g. `search_notes` vs
  `search_web`). A bare summary line is not done.
- **Reuse before writing.** Working integrations already exist for: Fastmail
  JMAP (`events/fastmail.py`), Whisper (`gateway/voice.py`), CalDAV
  (`tools/calendar.py`), Tavily (`tools/web_search.py`), OpenAI embeddings
  (`obsidian/embeddings.py`). Extend or extract from these; do not write a
  second client for a service we already talk to.
- **New tools need a wiring proof**, not just unit tests: `TestModel(call_tools=[])`
  + `last_model_request_parameters` to assert the tool reaches the model, or
  `FunctionModel` for run-through tests (see `tests/test_capabilities.py`).
  Two count assertions must be bumped: the N-tools test in
  `tests/test_capabilities.py` and `EXPECTED_TOOLS` in `tests/test_tool_registry.py`.
- **Locked decisions are locked.** `docs/plans/flutter-app-prd.md` and the
  "locked decisions" section of `docs/plans/flutter-architecture.md` record
  product/tech choices Jordan signed off on (preview-before-send voice, thin
  client, bundle id, http-not-Dio...). If an implementation conflicts with one,
  flag it and ask — never silently redesign around it.
- Full user-level rules (uv, ruff, typing, commit style) come from the global
  CLAUDE.md; they all apply here.

## Operations (facts you cannot derive from this repo)

- **Railway project "JB-HomeBase"**, environment `production`, two services:
  - `jb_homebase` — the web service. Port 8000; the service must have `PORT=8000`
    set (Railway's healthcheck probes the PORT variable, not the Dockerfile
    EXPOSE). Healthcheck `GET /health` returns 503 on degraded config and
    **gates the deploy** — a broken config never replaces a healthy deploy.
    Prod URL: `https://jbhomebase-production.up.railway.app`.
  - `evals-cron` — same image, start command `uv run claw-eval run --all`,
    cron `0 3 * * *`, healthcheck disabled, restart Never. Its env vars are
    REFERENCES to the main service: `${{ jb_homebase.VAR }}`.
  - **Always pass `-s <service>` to every `railway` command.** The CLI's sticky
    default service has landed vars on `evals-cron` instead of the web service
    before, which killed the workout bot on the next redeploy (2026-07-05).
    Verify on the target service after setting anything.
- **Push to `main` = production deploy.** After any push, verify with the
  `deploy-verify` skill: /health OK is necessary but not sufficient — confirm
  the new commit SHA is the active deploy and exercise the changed surface.
- **Secrets live in Infisical**: `infisical run --env=dev -- <cmd>` for local
  runs (evals, seed scripts). Never run interactive auth (`railway login`,
  `infisical login`) — ask Jordan to run it with the `!` prefix.
- **Incident history** (why the invariants above exist): sonnet-4 retirement
  silently downed both bots for ~3 weeks (evals stayed green because they pin
  their own model) → /health now validates DB models; Railway edge replays
  requests with no response after ~20s → every slow endpoint converges on an
  idempotency key; a `railway variables` call without `-s` broke the workout
  bot; `pydantic-evals` swallows task-fn exceptions → `claw-eval` fails fast on
  bad settings, and low case counts usually mean infra, not regression.

## Commands

```bash
uv run uvicorn jordan_claw.main:app --reload   # local gateway (stub tokens only!)
uv run pytest tests/test_x.py::test_y -v       # single test (don't run full suite unasked)
uv run ruff check . && uv run ruff format --check .
infisical run --env=dev -- uv run claw-eval run <dataset>   # eval run (~$0.10)
infisical run --env=dev -- uv run python -m evals.seed_corpus
cd flutter_app && flutter test                  # widget/unit tests (mock mode)
cd flutter_app && dart run build_runner build --delete-conflicting-outputs  # after @Riverpod changes
```

Flutter live mode and the on-simulator integration test: see
`flutter_app/README.md` (current and accurate).

## Doc trust map

| Doc | Status |
|---|---|
| `docs/architecture.md` | Maintained system map — keep it updated when flows change |
| `docs/evals.md`, `docs/observability.md` | Current, operational |
| `docs/jordan-claw-lessons-learned.md` | Current through Phase 3; the "why" behind invariants |
| `flutter_app/README.md` | Current (live mode, slugs, stub rule) |
| `docs/claw-main-prompt-reference.md` | STALE snapshot (Apr 2026, 4-tool Sonnet-4 era). Prompt truth: `agents.system_prompt` in DB + tool docstrings in code |
| `docs/plans/flutter-architecture.md` | Stale on design/IA/theming (trust the code); current on locked stack decisions and backend-wiring roadmap |
| `docs/superpowers/` | Historical point-in-time specs/plans, not runbooks |

## Verification before done

Global rules apply, with repo specifics: a DB write is done when you've queried
the row back; a deploy is done when the new SHA is live AND the changed surface
answers correctly (not when CI is green); an agent change is done when a real
message round-trips through the changed path (Telegram message, `/app/messages`
curl, or the integration test) — not when mocked unit tests pass.
