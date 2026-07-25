# Phase 1 agent upgrades — what shipped

Branch `feature/phase1-agent-upgrades`, 2026-07-25. Five tasks: history-trim
verification, cross-agent read access, reminders, weekly training review, model
config indirection.

## Deploy runbook (order is load-bearing)

1. **Before merging**: run migrations `016` (reminder schema) and `019` (org
   default model schema) in the Supabase SQL Editor. Both are additive and safe
   for the currently deployed code. `/health` on the new code queries
   `organizations.default_model` on every report, so a merge before 019 fails
   the deploy healthcheck (old deploy stays live — by design).
2. Merge the PR; Railway deploys; verify with the deploy-verify skill.
3. **After the new SHA is live**: run `017` (reminders grant + claw-main prompt
   guidance), `018` (weekly review schedule seed), `020` (null both agent
   models to inherit the org default). All idempotent. Then re-check `/health`
   and read back the rows (verify queries are in each migration's footer).

Migration `015` (read-only grants + prompt guidance) was already applied to
prod on 2026-07-25 with read-back verification. Until the merge, claw-main's
prompt mentions workout read tools it does not have yet; the deployed
`resolve_capabilities` skips the unknown ids safely. Merging promptly closes
that window.

## Task 1 — history trim budget: not a bug

`trim_history_processor` (agents/factory.py) already applies `max_tokens=4000`
as a real token budget: `max_chars = max_tokens * CHARS_PER_TOKEN` (= 16k
chars), the same 4-chars-per-token estimator `memory/reader.py` uses for the
500-token memory block. The "4000-token char budget" doc phrasing was
misleading, not the code. Clarified docstring + architecture.md, added
`test_trim_budget_is_tokens_not_chars` pinning the unit semantics (~8,800
chars survive untouched; a chars-misread would drop most of them).

## Task 2 — cross-agent read access

New capability groups in `agents/capabilities.py`, reusing the existing tool
fns (no forks):

- `workout_readonly` → get_workout_profile, get_workout_plan,
  get_recent_workouts. Granted to **claw-main**.
- `obsidian_readonly` → search_notes, read_note. Granted to **workout-coach**.

Never grant a `*_readonly` group alongside its full group (duplicate tool
names). Wiring proofs live in `tests/test_capabilities.py`
(`test_claw_main_gets_workout_reads_but_no_workout_writes`,
`test_workout_coach_gets_note_reads_but_no_note_writes`).

### Prompt diffs applied (migration 015, verified by read-back, idempotent on re-run)

claw-main — appended:

> You have read-only access to Jordan's training data through
> get_workout_profile, get_workout_plan, and get_recent_workouts. Use them to
> answer questions about his training, his plan, or recent workouts. Do not
> coach, revise plans, or log workouts, and do not offer to. For coaching,
> plan changes, or logging a session, tell Jordan to message the workout
> coach bot.

workout-coach — appended:

> You can search Jordan's saved notes with search_notes and read one with
> read_note. Use them for training-relevant research he has saved, like
> articles on running, strength, nutrition, or recovery. Do not use them for
> anything outside coaching. You cannot create notes.

## Task 3 — reminders

Built on `proactive_schedules`, no new subsystem.

Schema (migration 016): `cron_expression` now nullable, new nullable `run_at
timestamptz` (one-shot), new `source text NOT NULL DEFAULT 'system'`
('system' | 'reminder'), CHECK that one of cron/run_at is set.

Runtime: `should_run` fires a one-shot when `now >= run_at` and it has never
run; `dispatch_task` disables it after sending. New task_type `reminder`
delivers `config.message` verbatim (no LLM). Reminder dedup uses a 5-minute
`was_sent_within` window instead of `was_sent_today` so sub-daily recurring
reminders work; the window still guards the scheduler's >60s dispatch race.

Tools (capability `reminders`, on claw-main after 017): `set_reminder`
(exactly one of run_at/cron; naive times read as US Central; past times and
bad crons refused), `list_reminders` (only `source='reminder'` rows — system
jobs are invisible), `cancel_reminder` (refuses non-reminder rows; disables,
never deletes — `proactive_messages` FKs the schedule row).

### Prompt diff pending (migration 017, run after deploy)

claw-main — appends:

> You can set reminders. When Jordan asks to be reminded of something, call
> current_datetime first, work out the absolute time in US Central, and create
> the reminder with set_reminder: run_at for one-off reminders, cron for
> recurring ones. State the resolved absolute time back to him in your reply.
> Use list_reminders and cancel_reminder to manage them. Reminders are not
> calendar events; use schedule_event only when Jordan wants something on the
> calendar.

## Task 4 — weekly training review

New task_type `weekly_training_review` (`proactive/executors.py`), seeded by
migration 018: Sunday 18:00 America/Chicago, targets workout-coach. Pulls the
active plan and this week's logs (Monday-forward), prompts the coach to
compare logs to plan — done / missed / one-two adjustments, move sessions
missed twice+, under 10 short sentences. No plan or no logs this week
short-circuits to a deterministic one-liner plus one question, so a fake
review cannot be composed. Seed is idempotent via the (org_id, name) unique
constraint.

Follow-up: an eval case for the review prompt needs a new dataset + task fn in
the evals harness (fixture week of logs); not done in this phase.

## Task 5 — model config indirection

`organizations.default_model` (migration 019, backfilled to
`anthropic:claude-sonnet-5`) + nullable `agents.model`. Resolution:
`db/agents.py::resolve_model` — agent row override if set, else org default,
else ValueError. `get_agent_config` returns a resolved `AgentConfig`, so all
callers are unchanged. `/health` validates the resolved model and degrades
when neither level is set. Migration 020 nulls both agent rows (inherit); a
per-agent pin for a future cheaper-model split is one UPDATE.

## Test/tooling deltas

- Registry: 9 capability groups, 20 distinct tools (was 6 / 17). Count
  assertions bumped in `tests/test_capabilities.py` and
  `tests/test_tool_registry.py`.
- New test files: `tests/test_reminder_tools.py`. Extended:
  test_proactive_scheduler (one-shot semantics), test_proactive_delivery
  (reminder dedup), test_db_proactive, test_proactive_executors (weekly
  review), test_health (resolved-model validation), test_agents (resolution
  order + trim units).
- Full suite: 363 passed at branch tip.

## Phase 2 hooks left as TODOs

- `agents/capabilities.py` — agent-to-agent delegation supersedes the
  read-only mirror groups.
- `tools/workout.py` — HealthKit/Strava ingestion lands logs without typing.
