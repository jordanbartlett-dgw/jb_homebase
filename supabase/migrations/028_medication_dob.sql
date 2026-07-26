-- Med-check: date of birth on the medication profile (emergency one-pager
-- prints it when provided; prompt v3 already expects it).
-- Deploy order: SCHEMA change, run in the Supabase SQL Editor BEFORE
-- merging the code that reads/writes this column. Additive; current code
-- never touches it until then.
ALTER TABLE medication_profiles ADD COLUMN IF NOT EXISTS date_of_birth date;

SELECT pg_notify('pgrst', 'reload schema');
