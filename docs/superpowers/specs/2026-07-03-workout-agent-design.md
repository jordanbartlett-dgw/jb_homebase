# Workout Coach Agent Design

**Date:** 2026-07-03
**Status:** Draft, pending Jordan's approval
**Depends on:** Existing Claw platform (agents table, BASE_TOOLSET, proactive scheduler)

## Purpose

A second agent in Jordan's org: a workout coach. It runs an initial evaluation of
workout and nutrition preferences, builds a training plan from preferences and goals,
sends the day's session each morning, and adapts the plan from logged workouts.

Coaching scope: running/endurance, strength, mobility/recovery, and nutrition guidance.

This agent is the backend for the Flutter app's v1.1 Training room. Until that ships,
Jordan talks to it through a dedicated Telegram bot.

## Decisions Made

1. **Channel:** Second Telegram bot, second dispatcher in the same Railway service.
   Full agent routing (deferred decision #2) waits for the Flutter app's rooms.
2. **Intake:** Structured profile in a new `workout_profiles` table, filled
   conversationally through agent tools. Not the memory system.
3. **Plan:** Persisted in `workout_plans`, plus a proactive morning nudge with the
   day's session.
4. **Logging:** `workout_logs` table and a `log_workout` tool. Enables
   adherence-aware plan revisions now, feeds the Flutter mileage chart later.

## Data Model (migration 008)

### workout_profiles

One row per org.

| Column | Type | Notes |
|---|---|---|
| org_id | uuid PK, FK organizations | |
| goals | jsonb | e.g. race target, strength targets, weight |
| experience | text | |
| training_days | jsonb | days per week, time windows |
| equipment | jsonb | |
| injuries | text | constraints and history |
| nutrition | jsonb | preferences, restrictions, macro targets |
| baseline | jsonb | current weekly mileage, key lifts |
| updated_at | timestamptz | |

All content fields nullable. Profile counts as complete when goals, experience,
and training_days are non-null. Completeness is judged by the agent, not a column.

### workout_plans

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id | uuid FK | |
| status | text | check: active, archived |
| starts_on | date | |
| weeks | jsonb | weeks -> days -> sessions (type, description, targets) |
| rationale | text | why the plan is shaped this way |
| created_at, updated_at | timestamptz | |

Partial unique index: one active plan per org. Saving a new plan archives the old one.

### workout_logs

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| org_id | uuid FK | |
| plan_id | uuid FK nullable | |
| logged_date | date | |
| activity | text | check: run, strength, mobility, rest, other |
| details | jsonb | distance, duration, exercises, RPE |
| notes | text | free text ("legs felt heavy") |
| created_at | timestamptz | |

### Chat ID moves from org to agent

Two bots in one org would stomp `organizations.telegram_chat_id` (every incoming
message writes it). Fix in the same migration:

- Add `agents.telegram_chat_id bigint`.
- Backfill claw-main's value from the org row.
- Drop `organizations.telegram_chat_id`. Only `db/proactive.py` touches it.

### Agent row

`workout-coach` inserted by the migration: same model as claw-main, coach system
prompt, tools list below. Migration ends with the PostgREST `pg_notify` schema
cache reload.

## Agent Behavior

### Tools (new, registered on BASE_TOOLSET)

| Tool | Does |
|---|---|
| get_workout_profile | Read the profile, report which core fields are missing |
| save_workout_profile | Partial upsert. Each intake answer saves immediately |
| get_workout_plan | Read the active plan |
| save_workout_plan | Create new active plan, archive the previous one |
| log_workout | Insert a workout log |
| get_recent_workouts | Recent logs for plan revision context |

Reused tools: `current_datetime`, `check_calendar`, `schedule_event` (plan around
meetings), `recall_memory`.

Memory is org-scoped, so the coach and claw-main share long-term memory. In a
single-user org that is a feature: the coach knows about Jordan's schedule pressure,
claw-main knows he is training for something.

### Intake (prompt-driven, no intake code)

The system prompt instructs the coach to:

1. Call `get_workout_profile` at the start of a conversation.
2. If incomplete: run the evaluation. One question at a time, covering goals,
   baseline, schedule, equipment, injuries, nutrition preferences. Save each
   answer with `save_workout_profile` as it goes, so a dropped conversation
   loses nothing.
3. When complete: propose a draft plan (running, strength, mobility, nutrition
   guidance), iterate with Jordan, then `save_workout_plan`.
4. On later conversations: read profile, plan, and recent logs. Revise the plan
   when goals change or logs show the plan is not landing.

### New code layout

```
src/jordan_claw/workout/models.py   WorkoutProfile, WorkoutPlan, PlanWeek, PlanDay, WorkoutLog
src/jordan_claw/db/workout.py       profile/plan/log queries
src/jordan_claw/tools/workout.py    the six tools
```

## Channel and Proactive

### Second dispatcher

- Settings: `workout_telegram_bot_token` (empty default disables the feature),
  `workout_agent_slug` (default `workout-coach`).
- `main.py` lifespan: when the token is set, create a second `Bot`, reuse
  `create_telegram_dispatcher(agent_slug="workout-coach")`, start a second
  polling task.
- `save_telegram_chat_id` / `get_telegram_chat_id` become per-agent
  (org_id + agent_slug), reading the new `agents.telegram_chat_id`.

### Daily workout nudge

- New `daily_workout` executor: reads active plan, today's date, recent logs.
  Composes the morning message through the workout agent (same pattern as
  morning briefing). Returns empty string on rest days with nothing to say,
  which suppresses the send.
- Schedule row: cron `0 6 * * *`, America/Chicago, config
  `{"agent_slug": "workout-coach"}`.
- Scheduler holds `{agent_slug: Bot}` and `dispatch_task` picks the bot by the
  schedule's agent slug. Proactive messages from claw-main schedules keep using
  the claw-main bot.

## Error Handling

- Missing chat ID for the workout bot (Jordan has not sent /start yet): proactive
  send logs a warning and skips, existing behavior.
- Tool failures surface as tool errors to the agent, which apologizes and retries
  or asks Jordan to retry. No new error types (deferred decision #5 unchanged).
- Second bot token unset: service runs exactly as today, no workout features.

## Testing

- Unit tests per new module, following existing patterns: mocked supabase query
  chains for `db/workout.py`, pydantic-ai "test" model and FilteredToolset
  inspection for tools, executor tests like the morning-briefing ones.
- Dispatcher wiring test: token set spawns two pollers, unset spawns one.
- Verification per CLAUDE.md: after migration, query the new tables and show rows.
  After deploy, /start the bot and run one real intake exchange.

## Rollout

1. Create bot with BotFather (@jb_workout_bot or similar).
2. Apply migration 008, run pg_notify reload, verify tables exist.
3. Set `WORKOUT_TELEGRAM_BOT_TOKEN` in Railway.
4. Push to main (auto-deploy), verify deploy.
5. /start the bot, run the intake, approve the first plan.

## Out of Scope (v1)

- Meal-level nutrition tracking or food logging.
- Wearable/Strava integration (logs are chat-entered).
- Plan visualization (that is the Flutter Training room, v1.1).
- Eval dataset for the coach (add once behavior stabilizes).
- Agent routing in the main bot (deferred decision #2 stands until Flutter rooms).
