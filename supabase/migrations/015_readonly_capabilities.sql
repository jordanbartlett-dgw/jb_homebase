-- Read-only cross-agent capability grants + prompt guidance (Phase 1, Task 2).
-- Data-only: no schema change, no pg_notify needed.
-- Deploy order: run AFTER the code deploy that adds workout_readonly /
-- obsidian_readonly to CAPABILITY_REGISTRY. (Unknown ids are skipped safely,
-- but the prompt guidance below references the tools, so grant once code is live.)
-- Idempotent: guarded array_append + NOT LIKE guards on the appended paragraphs.

UPDATE agents SET capabilities = array_append(capabilities, 'workout_readonly')
WHERE slug = 'claw-main' AND NOT ('workout_readonly' = ANY(capabilities));

UPDATE agents SET capabilities = array_append(capabilities, 'obsidian_readonly')
WHERE slug = 'workout-coach' AND NOT ('obsidian_readonly' = ANY(capabilities));

UPDATE agents
SET system_prompt = system_prompt || E'\n\n' ||
  'You have read-only access to Jordan''s training data through get_workout_profile, get_workout_plan, and get_recent_workouts. Use them to answer questions about his training, his plan, or recent workouts. Do not coach, revise plans, or log workouts, and do not offer to. For coaching, plan changes, or logging a session, tell Jordan to message the workout coach bot.'
WHERE slug = 'claw-main'
  AND system_prompt NOT LIKE '%read-only access to Jordan''s training data%';

UPDATE agents
SET system_prompt = system_prompt || E'\n\n' ||
  'You can search Jordan''s saved notes with search_notes and read one with read_note. Use them for training-relevant research he has saved, like articles on running, strength, nutrition, or recovery. Do not use them for anything outside coaching. You cannot create notes.'
WHERE slug = 'workout-coach'
  AND system_prompt NOT LIKE '%search Jordan''s saved notes%';

-- Verify:
-- SELECT slug, capabilities FROM agents WHERE slug IN ('claw-main','workout-coach');
