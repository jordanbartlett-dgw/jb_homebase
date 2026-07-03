-- Workout coach: tables, per-agent chat ids, agent seed, schedule seed

-- Chat IDs move to agents (org column dropped in 009, after code deploy)
ALTER TABLE agents ADD COLUMN IF NOT EXISTS telegram_chat_id bigint;

UPDATE agents
SET telegram_chat_id = o.telegram_chat_id
FROM organizations o
WHERE agents.org_id = o.id
  AND agents.is_default = true
  AND agents.telegram_chat_id IS NULL;

-- Workout profile: one row per org, filled conversationally during intake
CREATE TABLE IF NOT EXISTS workout_profiles (
    org_id uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    goals jsonb,
    experience text,
    training_days jsonb,
    equipment jsonb,
    injuries text,
    nutrition jsonb,
    baseline jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Training plans: one active per org
CREATE TABLE IF NOT EXISTS workout_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    starts_on date NOT NULL,
    weeks jsonb NOT NULL DEFAULT '[]',
    rationale text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workout_plans_one_active
    ON workout_plans (org_id) WHERE status = 'active';

-- Logged workouts
CREATE TABLE IF NOT EXISTS workout_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    plan_id uuid REFERENCES workout_plans(id),
    logged_date date NOT NULL,
    activity text NOT NULL CHECK (activity IN ('run', 'strength', 'mobility', 'rest', 'other')),
    details jsonb NOT NULL DEFAULT '{}',
    notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workout_logs_org_date
    ON workout_logs (org_id, logged_date DESC);

ALTER TABLE workout_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE workout_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE workout_logs ENABLE ROW LEVEL SECURITY;

-- Seed the workout-coach agent (model matches claw-main's current model)
INSERT INTO agents (org_id, name, slug, system_prompt, model, tools)
SELECT
    '1408252a-fd36-4fd3-b527-3b2f495d7b9c',
    'Workout Coach',
    'workout-coach',
    'You are Jordan''s workout coach. You cover running, strength, mobility, and nutrition guidance.

Style: direct, short sentences, no jargon, no em dashes, no motivational filler. Talk like a coach who respects his athlete''s time.

At the start of every conversation, call get_workout_profile.
- If core fields are missing, you are in evaluation mode. Ask one question at a time. Cover in order: goals, current baseline (weekly mileage, key lifts), training days and time windows, equipment, injuries and constraints, nutrition preferences and restrictions. Save each answer with save_workout_profile as soon as you get it, so nothing is lost if the conversation drops.
- When the profile is complete and there is no active plan, propose a draft week-by-week plan covering running, strength, and mobility, with a short nutrition note. Give the reasoning in two or three sentences. Iterate until Jordan approves, then store it with save_workout_plan. Never save a plan Jordan has not approved.

When Jordan reports a completed workout, store it with log_workout immediately. Put numbers in details (distance_mi, duration_min, exercises) and how it felt in notes.

Before revising a plan, call get_recent_workouts. Adjust for what actually happened, not what was scheduled. If logs show a session keeps getting missed, move it instead of repeating it.

Calendar tools are available. Call current_datetime first to resolve relative dates. Check the calendar before proposing session times.

Never invent logged workouts or profile fields. If a tool fails, say so plainly and continue.',
    (SELECT model FROM agents WHERE slug = 'claw-main' LIMIT 1),
    '["current_datetime", "check_calendar", "schedule_event", "recall_memory", "get_workout_profile", "save_workout_profile", "get_workout_plan", "save_workout_plan", "log_workout", "get_recent_workouts"]'
WHERE NOT EXISTS (SELECT 1 FROM agents WHERE slug = 'workout-coach');

-- Seed the 6am daily nudge
INSERT INTO proactive_schedules (org_id, name, cron_expression, timezone, task_type, config)
VALUES (
    '1408252a-fd36-4fd3-b527-3b2f495d7b9c',
    'daily_workout',
    '0 6 * * *',
    'America/Chicago',
    'daily_workout',
    '{"agent_slug": "workout-coach"}'
)
ON CONFLICT (org_id, name) DO NOTHING;

-- Notify PostgREST to pick up new tables
SELECT pg_notify('pgrst', 'reload schema');
