-- Grant the reminders capability to claw-main + prompt guidance (Phase 1, Task 3).
-- Data-only. Deploy order: run AFTER migration 016 AND after the code deploy
-- that adds the reminders capability — set_reminder writes run_at/source and
-- fails against the pre-016 schema.
-- Idempotent: guarded array_append + NOT LIKE guard on the appended paragraph.

UPDATE agents SET capabilities = array_append(capabilities, 'reminders')
WHERE slug = 'claw-main' AND NOT ('reminders' = ANY(capabilities));

UPDATE agents
SET system_prompt = system_prompt || E'\n\n' ||
  'You can set reminders. When Jordan asks to be reminded of something, call current_datetime first, work out the absolute time in US Central, and create the reminder with set_reminder: run_at for one-off reminders, cron for recurring ones. State the resolved absolute time back to him in your reply. Use list_reminders and cancel_reminder to manage them. Reminders are not calendar events; use schedule_event only when Jordan wants something on the calendar.'
WHERE slug = 'claw-main'
  AND system_prompt NOT LIKE '%create the reminder with set_reminder%';

-- Verify:
-- SELECT slug, capabilities FROM agents WHERE slug = 'claw-main';
