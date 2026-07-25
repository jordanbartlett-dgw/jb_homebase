-- Med-check phase 3: care profile + generated-document tracking.
-- Deploy order: SCHEMA change — run in the Supabase SQL Editor BEFORE merging
-- the phase-3 code. Additive; current code touches neither table.
CREATE TABLE IF NOT EXISTS care_profiles (
    org_id uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    diagnoses jsonb NOT NULL DEFAULT '[]',
    critical_flags jsonb NOT NULL DEFAULT '[]',
    seizure_plan text,
    baselines text,
    communication text,
    routines text,
    escalation text,
    contacts jsonb NOT NULL DEFAULT '[]',
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS care_documents (
    org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    doc_type text NOT NULL CHECK (doc_type IN ('emergency', 'handoff')),
    source_hash text NOT NULL,
    note_title text NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, doc_type)
);

ALTER TABLE care_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE care_documents ENABLE ROW LEVEL SECURITY;

-- Seed the first critical flag (spec-mandated; Jordan can edit or add via the agent)
INSERT INTO care_profiles (org_id, critical_flags)
VALUES (
    '1408252a-fd36-4fd3-b527-3b2f495d7b9c',
    '["Congenital Long QT — avoid QT-prolonging medications (CredibleMeds list); confirm any new drug with cardiology."]'
)
ON CONFLICT (org_id) DO NOTHING;

SELECT pg_notify('pgrst', 'reload schema');
