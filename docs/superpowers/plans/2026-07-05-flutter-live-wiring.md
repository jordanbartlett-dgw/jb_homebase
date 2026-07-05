# Flutter Live Wiring — PR2 (2026-07-05)

Goal: the JB Homebase app talks to the real Jordan Claw gateway — text chat and
voice — so it can go live on Jordan's device. Stacked branch `feature/flutter-live`
on top of `feature/flutter-app` (PR #13).

## What already exists (landed on main 2026-07-04)

- `POST /voice` — bearer `CLAW_APP_TOKEN`, raw audio bytes → `{transcript,
  agent_slug, reply}`. Whisper transcription, haiku classifier route,
  idempotent against Railway ~20s edge replays.
- `handle_app_message` (gateway/voice.py) — full gateway lifecycle for
  app-originated utterances, replay-race convergence included.
- Interim auth decision (PR2 plan doc): static bearer `CLAW_APP_TOKEN` until
  real Flutter auth lands. Passkey/AASA work stays blocked on Apple Team ID +
  `auth.jbhomebase.app` hostname.

## Phase A — backend: `POST /app/messages`

Text-chat twin of `/voice`, minus transcription/classification (the app's agent
picker makes the slug explicit).

- New `gateway/app_chat.py`: `AppMessageRequest{text, agent_slug,
  idempotency_key}`, `AppMessageResponse{agent_slug, reply, conversation_id}`,
  `channel_message_id()` key builder, `replay_app_response()`.
- Generalize `handle_app_message` with `channel` / `channel_thread_id` /
  `run_kind` kwargs; voice defaults unchanged.
- Conversation identity: `channel="app"`, `channel_thread_id=<agent_slug>` —
  one gateway conversation per agent, matching the app's thread-per-agent UI.
- Same replay convergence as voice: pre-check by key → await original reply;
  `OriginalRunIncompleteError` → 504. Client sends one UUID idempotency key
  per message.
- Blocking POST (no streaming): the agent runner is not streaming today; the
  architecture doc's `EventStreamDecoder` hedge stays client-side for later.

## Phase B — Flutter: replace mocks at the four integration points

- `api_client.dart` → real client. `GATEWAY_URL` + `CLAW_APP_TOKEN` via
  `--dart-define`; POST `/app/messages` and `/voice` (with
  `X-Idempotency-Key`).
- `app_state.dart` send flow → gateway call replaces the mock reply timer;
  typing dots while awaiting; error bubble on failure.
- Voice preview send → `/voice`, reply lands in the returned agent's thread.
- Sign-in: when a dart-define token is present, the passkey screen passes
  straight through (real auth is a later PR).
- Daily Digest stays mock (`/api/today/cards` does not exist yet).

## Phase C — verify

Backend: full pytest suite. App: `dart analyze --fatal-infos`, `flutter test`,
then drive the simulator against the gateway run locally via
`infisical run --env=prod -- uv run uvicorn ...` and confirm a real
claw-main round trip.

## Phase D — device (blocked on Jordan)

Apple Team ID for signing → run on physical iPhone; `CLAW_APP_TOKEN` value
into the run config. TestFlight later.
