-- Med-check agent: medication profile table (mirrors workout_profiles).
-- Deploy order: SCHEMA change — run in the Supabase SQL Editor BEFORE merging
-- the med-check code. Additive; current code never touches this table.
CREATE TABLE IF NOT EXISTS medication_profiles (
    org_id uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    medications jsonb NOT NULL DEFAULT '[]',
    allergies text,
    notes text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE medication_profiles ENABLE ROW LEVEL SECURITY;

-- PostgREST schema cache reload (function form; NOTIFY fails in the SQL Editor)
SELECT pg_notify('pgrst', 'reload schema');
