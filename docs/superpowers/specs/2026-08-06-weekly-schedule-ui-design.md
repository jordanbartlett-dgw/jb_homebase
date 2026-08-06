# Weekly Schedule UI with Progressive Overload Analysis

Date: 2026-08-06
Status: approved design, pre-implementation

## What this is

A weekly training view in the JB Homebase app. It shows the current
Monday-Sunday week: past days show what was logged with a progressive
overload verdict, future days show what the plan schedules. Server
computes everything. The app renders it.

Decisions locked with Jordan during brainstorming:

- UI lives on Home: a "This Week" card on the dashboard plus a full
  screen at `/home/training`. Same pattern as digest and calendar.
- Overload verdicts are deterministic Python. No LLM in the path.
- Baseline is the previous same-activity session, per-exercise matching
  for strength.
- Week window is the current calendar week, Monday through Sunday,
  Central time. Current week only in v1. No paging into past weeks.
- Verdict UI is a badge plus a one-line reason. Tap for full comparison.
- App-only in v1. The coach agent does not get an analysis tool yet.
  The analysis module is pure so wiring it in later is one tool away.

## Architecture

Three new pieces, one groove already worn by the Today feature:

1. `src/jordan_claw/workout/analysis.py`. Pure functions, no I/O.
2. `src/jordan_claw/gateway/app_week.py` plus `GET /app/workout/week`
   mounted in `main.py` beside `/app/today`.
3. Flutter: `ThisWeekCard` on the dashboard, `WeekScheduleScreen` at
   `/home/training`, api models, repository, Riverpod controller, and a
   mock-mode fixture. All mirroring the `today` feature files.

## Overload semantics (analysis.py)

Verdict enum: `positive`, `none`, `negative`, `no_baseline`. Only `run`
and `strength` logs are scored. Mobility, rest, and other are unscored
and carry no badge.

Baseline, runs: the most recent earlier run log within a 45-day
lookback. No such log, or details that cannot be parsed on either
side, means `no_baseline`.

Baseline, strength: per exercise. Each exercise in the log matches
against the most recent earlier strength log within the lookback that
contains that exercise. This keeps split routines comparable (push day
compares against the last push day, not yesterday's leg day).

Runs. Compare distance (`distance_mi`) and pace (duration divided by
distance), each classed better, same, or worse with a 3% tolerance.
Aggregate: any metric better and none worse is `positive`; any worse
and none better is `negative`; mixed or all-same is `none`. If both
logs carry only `duration_min`, longer is better.

Strength. Exercises match by normalized name (lowercase, trimmed).
Per matched exercise: heavier top weight is better; same weight with
more reps or volume (weight x reps x sets where available) is better;
lighter or fewer is worse. Aggregate with the same rule as runs. Zero
matched exercises across the lookback means `no_baseline`.

Reason line: built from the real comparison, referencing the baseline
date per comparison. Examples: `+0.4 mi at same pace vs Jul 30`,
`+10 lb squat (vs Jul 29), -1 rep bench (vs Jul 27)`.

The analysis never raises. Malformed jsonb degrades to `no_baseline`
with a reason that says so. The 3% tolerance and 45-day lookback are
named constants in one place. Sanity-check both against real prod
`details` rows before finalizing (Infisical session needs re-auth
first; run `infisical login` via the `!` prefix).

## Endpoint contract

`GET /app/workout/week` returns:

- `week_start`, `week_end`: ISO dates for the current Mon-Sun window in
  `America/Chicago`.
- `timezone`: the tz name.
- `plan_status`: `active`, `none`, or `ended` (date is past the plan's
  last week).
- `days`: exactly 7 entries, Monday first:
  - `date`, `is_today`
  - `planned`: `{session_type, description, targets}` or null
  - `logs`: list of `{id, activity, details, notes, verdict, reason}`.
    `verdict` and `reason` are null on unscored activities.
  - `day_status`: `logged`, `missed` (past day, planned non-rest
    session, no log), `rest` (planned rest), `upcoming` (future day
    with a planned session), `today` (today with no log yet; today
    with a log is `logged`), or `empty` (no planned session and no
    log, past or future).

Plan mapping is arithmetic, no LLM: `(date - starts_on).days // 7`
indexes into `weeks`; weekday name matches `PlanDay.day`. Days before
`starts_on` or past the last week get `planned: null`.

No active plan: all `planned` null, `plan_status: "none"`, logs and
verdicts still returned.

Data access: one query for the active plan, one query for logs from
`week_start - 45 days` forward. That single log window feeds both the
week's rows and every baseline lookup. No N+1.

## Flutter UI

`ThisWeekCard`, placed on the dashboard between UP NEXT and UPDATES:

- Today's planned session (type plus short description).
- A 7-chip week strip, one chip per day, colored by status: verdict
  tint for logged days (positive green, none neutral, negative red),
  hollow for upcoming, muted for rest, missed, and empty.
- Tap anywhere opens `/home/training`.
- No active plan: card reads "No active plan. Ask your coach."

`WeekScheduleScreen` at `/home/training`, registered beside
`/home/calendar`:

- Vertical list of 7 day tiles, today highlighted.
- Past logged days: activity, key numbers, verdict badge, reason line.
  Tap opens a bottom sheet with full details, notes, and the
  comparison against baseline.
- Future days: planned session type and description.
- Missed days: marked plainly as missed.
- Pull-to-refresh.

State: `workout_api_models.dart`, a repository, and an AsyncNotifier
controller copied from the `today` pattern. The card and the screen
share one provider, so one fetch per load. `mock_data.dart` gets a
sample week so mock mode keeps working.

## Error handling

- No plan, no logs, empty days: normal states, rendered as such, never
  errors.
- DB failure in the endpoint: standard 500, same as the other `/app`
  routes.
- Flutter: reuse the Today loading-card, error-card, and retry pattern.
- Analysis layer: total function, never raises on bad data.

## Testing

- Unit tests on `analysis.py`: run faster, slower, mixed; strength up,
  down, mixed; missing keys; malformed details; no baseline; week
  mapping edges (plan started mid-week, plan ended, no plan).
- Endpoint test following the existing `tests/test_app_*` pattern.
- Flutter widget test: week screen renders the mock week; badges show
  the right verdict states.
- No new agent tools in this slice, so the two tool-count assertions
  (`tests/test_capabilities.py`, `tests/test_tool_registry.py`) stay
  untouched.

## Out of scope for v1

- Week paging into the past.
- A coach-agent tool exposing the analysis.
- Any change to `/app/today`.
- HealthKit or Strava ingestion (noted as phase-2 in `tools/workout.py`).
