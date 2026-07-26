# AgentMail inbox + code mode for Claw Main — design

Date: 2026-07-26. Status: approved by Jordan (design conversation, this date).
Scope: give `claw-main` its own email inbox via AgentMail, and grant it the
pydantic-ai-harness CodeMode capability. Three PRs, each deployed and verified
before the next starts.

## Locked decisions (Jordan, 2026-07-26)

- Inbox: the existing `jordanb@agentmail.to` (verified via API; the address is
  `.to`, not `.com`). API key already in Infisical as `AGENTMAIL_API_KEY`.
- Inbound path: poll watcher mirroring the Fastmail JMAP watcher. No webhook,
  no svix dependency.
- Send policy: the agent sends or replies only when Jordan asks in chat.
  Autonomous inbound handling produces summaries as app artifacts, never
  outbound email. Email bodies are fenced as untrusted input.
- Sequencing: framework upgrade first as its own PR, then email, then code mode.

## PR 1 — framework upgrade

`pydantic-ai-harness` 0.11.0 requires `pydantic-ai-slim>=2.14.1`; the repo is
on 2.5.0. This PR is only the upgrade, so a regression attributes cleanly.

- Bump `pydantic-ai-slim[anthropic]` and `pydantic-evals` in lockstep (both
  stay `<3`). Read the changelogs for the 2.5 to 2.14 span before code changes.
- Gate: full test suite, ruff, then `claw-eval run --all` against committed
  baselines (~$0.65). Any score below baseline − 0.05 blocks the merge.
- Deploy, then `deploy-verify`: new SHA active, `/health` OK, one real message
  through each agent.

## PR 2 — email capability

### Dependency

`agentmail` (async SDK). Approved by Jordan as part of this design.

### Config

- `Settings`: `AGENTMAIL_API_KEY` (default `""`; empty = email capability and
  watcher disabled, matching the empty-string sentinel pattern) and
  `AGENTMAIL_INBOX_ID` (default `jordanb@agentmail.to`).
- `AgentDeps`: defaulted fields `agentmail_api_key: str = ""` and
  `agentmail_inbox_id: str = ""`. Plumb at every `AgentDeps(` construction
  site: `gateway/router.py`, `events/pipeline.py`, `proactive/executors.py`.
- Railway: set both vars on the `jb_homebase` service with `-s jb_homebase`
  and verify on the target service. evals-cron does not need them (optional
  vars, stubbed tools in evals).

### Tools (`src/jordan_claw/tools/email.py`)

Four plain async fns taking `ctx: RunContext[AgentDeps]`, adapted from the
verified reference in the `agentmail-pydantic-ai` skill assets. The
`AsyncAgentMail` client is built from the deps key via a small cached helper,
never module-global.

- `send_email(to, subject, body)` — new outbound thread.
- `reply_to_email(message_id, body)` — reply to a specific message.
- `list_email_threads(limit)` — recent threads in the agent's inbox.
- `read_email_thread(thread_id)` — messages in a thread, newest-reply aware.

Docstrings carry the routing boundary: this is the agent's own inbox
(`jordanb@agentmail.to`) for sending and receiving mail on Jordan's behalf.
It is NOT Jordan's personal Fastmail; calendar and agenda questions go through
the calendar tools.

Body preference everywhere: `extracted_text or text or extracted_html or html`.
SDK sender field is `from_`.

### Registry and grant

- New `email` ToolGroup in `CAPABILITY_REGISTRY` with a description written
  for the classifier catalog.
- Migration 029 (data, idempotent `array_append` guarded by `NOT (... = ANY)`)
  grants `email` to `claw-main`. Code deploys first, then the grant
  (`resolve_capabilities` skips unknown ids, so order is safe either way).

### Inbound watcher (`events/agentmail.py`)

Mirror `events/fastmail.py::poll_fastmail` exactly:

- Task type `agentmail_watch` in `EXECUTOR_MAP`, scheduler passthrough like
  `fastmail_watch` (delivers per-email through the event pipeline itself).
- Schedule row: cron `*/5 * * * *`, America/Chicago, seeded in migration 029.
- Cursor in `watcher_cursors`; first poll seeds the cursor with no backfill.
- Each new inbound message fires
  `process_event(source="agentmail-email")` with per-message try/except
  isolation. Disabled when `AGENTMAIL_API_KEY` is empty.
- `event_triggers` row for `agentmail-email` (seeded in 029) targets
  `claw-main`. The prompt template fences the body in `<incoming_email>` tags,
  states the content is untrusted and instructions inside it must never be
  followed, and asks for a triage summary. Output lands in the app's Today
  artifacts feed via the normal proactive delivery path. It never sends email.

### Tests

- Unit tests for the four tools against a duck-typed fake client. No live
  calls, `models.ALLOW_MODEL_REQUESTS = False` where agents are built.
- Wiring proof: `TestModel(call_tools=[])` + `last_model_request_parameters`
  shows all four tool defs reach the model for an agent granted `email`.
- Count bumps: N-tools test in `tests/test_capabilities.py` and
  `EXPECTED_TOOLS` in `tests/test_tool_registry.py`, 33 to 37.
- Watcher unit test: cursor seed, new-message dispatch, empty-key disabled.

### Verification (prod)

- `SELECT slug, capabilities FROM agents` shows the grant.
- Real chat message asking Claw Main to send a test email; read the sent
  message back via the AgentMail API.
- One synthetic inbound email to `jordanb@agentmail.to`; confirm the artifact
  appears in the Today feed within one poll cycle.
- Logfire/usage_events show the runs.

## PR 3 — code mode

### Dependency

`pydantic-ai-harness[codemode]` (pulls `pydantic-monty`; in-process sandbox,
no external service). Approved by Jordan as part of this design.

### Registry change

- Widen `CAPABILITY_REGISTRY` to `dict[str, AbstractCapability[AgentDeps]]`
  and `resolve_capabilities` to match. ToolGroup entries unchanged.
- New entry: `CodeMode(id="code_mode", tools='all', description="Write
  sandboxed Python that composes the agent's other tools in one step.")`.
  Always-on once granted (no `defer_loading`; the id is stable regardless).
- Migration 030 grants `code_mode` to `claw-main`. Rollback is one UPDATE
  removing the id from the array.

### Behavior

Once granted, the model sees a single `run_code` tool and writes sandboxed
Python that calls the granted tools (loops, conditionals, parallel fan-out).
The Monty sandbox has no filesystem, env, network, or clock access of its own;
the wrapped tools remain the only side-effect surface. No `mount` or
`os_access` configured.

### Tests

- Wiring proof that `run_code` reaches the model for an agent granted
  `code_mode`.
- The exact-count assertions get a documented carve-out: CodeMode contributes
  no ToolGroup tools, so registry tool counts exclude it.

### Verification (prod)

A multi-tool prod message (for example, cross-referencing calendar and notes)
plus a Logfire check that the run went through `run_code` and the underlying
tools still executed.

## Error handling

Existing patterns throughout: per-message isolation in the watcher, empty
secret = feature off (never a crash), all runs through
`run_agent_instrumented` (tokens, cost, error taxonomy, budget guardrail).

## Out of scope

Custom email domain, webhook/real-time inbound, autonomous replies, drafts
workflow, email for workout-coach or med-check, deferred loading of either
capability. All can layer on later without reworking this design.
