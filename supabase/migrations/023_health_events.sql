-- Med-check phase 2: health event log + timeline display name.
-- Deploy order: SCHEMA change — run in the Supabase SQL Editor BEFORE merging
-- the phase-2 code. Additive; current code touches neither.
CREATE TABLE IF NOT EXISTS health_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    event_date date NOT NULL,
    category text NOT NULL CHECK (category IN (
        'milestone', 'seizure', 'breathing_episode', 'gi', 'sleep', 'motor',
        'communication', 'scoliosis_orthopedic', 'growth_measurement',
        'medication_change', 'appointment', 'illness', 'other'
    )),
    title text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}',
    notes text,
    severity text CHECK (severity IN ('mild', 'moderate', 'severe', 'er_visit')),
    logged_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_health_events_org_date
    ON health_events (org_id, event_date DESC);

ALTER TABLE health_events ENABLE ROW LEVEL SECURITY;

-- Controls the name shown on shared documents (timelines now, care docs in
-- phase 3). NULL = agent asks before generating.
ALTER TABLE medication_profiles ADD COLUMN IF NOT EXISTS timeline_display_name text;

SELECT pg_notify('pgrst', 'reload schema');
