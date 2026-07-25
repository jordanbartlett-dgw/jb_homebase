# JB Homebase — Flutter app (iOS)

Thin client over the FastAPI gateway. Replaces Telegram as the primary
channel. v1 is iOS-only. Android is deferred.

Design direction lives in `../docs/flutter-design/` (JB Homebase prototype)
and the PRD in `../docs/plans/flutter-app-prd.md`. Architecture decisions in
`../docs/plans/flutter-architecture.md` (note: the IA there predates the
JB Homebase design pivot — this README is current).

## Status

- **Text chat and conversation history are live gateway surfaces**: sends go to
  `POST /app/messages` with bearer `CLAW_APP_TOKEN` auth and one idempotency
  key per message; active threads hydrate after relaunch. History lists
  retained sessions, opens read-only transcripts, and New Chat archives the
  current session before the next send. Voice upload
  (`ApiClient.sendVoice` → `POST /voice`) is built and tested but unused —
  real audio capture (`record`) is the next feature.
- Still pending: Daily Digest and calendar (the dashboard shows an honest
  coming-next state instead of fabricated activity), voice overlay
  (placeholder transcript), passkey/magic-link screens (live builds skip
  them — the static token is the interim auth).
- `dart analyze --fatal-infos` clean; unit + widget + flow tests pass
  (`flutter test`); on-simulator integration test drives the live path
  (`integration_test/live_chat_test.dart`).

## The app

Passkey sign-in (tap-through mock) → three-tab shell with a floating pill
nav (NavigationRail on ≥ 840dp):

- **Home** — eyebrow date, Playfair greeting, honest Daily Digest placeholder,
  and horizontal agent dock.
- **Agents** — agent picker chips (Claw Main, Workout Coach), asymmetric
  chat bubbles, per-agent tinted typing indicator, tool-call chips,
  composer with mic (voice overlay) + send, and New Chat. Threads are
  per-agent Riverpod families, survive tab switches, and hydrate from the
  gateway after relaunch.
- **History** — retained app sessions grouped by date with agent identity,
  active-session state, cursor pagination, and read-only transcripts.

Voice: mic in the chat composer → recording overlay (animated waveform) →
transcript preview → Send appends to the active agent's thread.

## Design system

- Palette: black/white surfaces with cobalt `#3157F6` as the restrained
  accent. Dark mode follows the system.
- Type: Playfair Display for display moments, Inter for everything
  functional (google_fonts).
- 24pt card radius, soft diffuse shadows (`AppTheme.softShadow`).
- Tactility: `BouncyButton` (scale + haptic, no ripple), `FadeSlideIn`
  staggered entrances. Tokens in `lib/theme/`.

## Running it

```bash
cd flutter_app
flutter pub get
dart run build_runner build   # riverpod codegen (app_state.g.dart)
flutter run -d "iPhone 17"
```

Xcode 26.0 note: `device_info_plus` is pinned to 12.3.0 in
`pubspec.yaml` `dependency_overrides` — newer versions need the iOS 26.1
SDK. Drop the pin after upgrading Xcode.

### Running it live

Without dart-defines the app is the mock design build (what the widget
tests exercise). Two defines switch every surface that has a backend to
the real gateway and skip the sign-in screen:

```bash
flutter run -d "iPhone 17" \
  --dart-define=GATEWAY_URL=https://jbhomebase-production.up.railway.app \
  --dart-define=CLAW_APP_TOKEN=<token from Railway env>
```

The defines are baked into the binary, so relaunching the app from the
home screen keeps working after `flutter run` detaches. Live threads hydrate
from server-side conversation history, one gateway thread per agent. Agent ids in
`lib/shared/models/agent.dart` ARE
the gateway slugs — `claw-main`, `workout-coach`.

The live-path integration test runs against a local stub of
`/app/messages` and `/app/conversations/current` (see
`integration_test/live_chat_test.dart`). Don't run the real gateway locally —
it steals the prod Telegram bot's `getUpdates` polling.

## File map

```
lib/
  main.dart                    app entry, ProviderScope
  app.dart                     MaterialApp.router, light/dark theme
  theme/                       colors, typography, app_theme, spacing, motion
  routing/
    app_router.dart            GoRouter: auth redirect + StatefulShellRoute
    routes.dart                /home /agents /history /voice /auth/*
  shell/homebase_shell.dart    floating pill nav / NavigationRail
  features/
    home/                      dashboard (digest, agent dock, previews)
    chat/                      chat screen + typing indicator, tool chips
    history/                   history list + read-only transcript
    auth/                      passkey + magic link
    voice/                     capture overlay + preview
  shared/
    models/                    Agent, Message, Conversation
    widgets/                   BouncyButton, FadeSlideIn, MessageBubble, Entrance
    api/                       gateway client + wire payloads + mock data
  data/repositories/           API payload → domain model boundaries
  state/app_state.dart         Riverpod: auth, active agent, threads, typing
  state/conversation_state.dart Riverpod: history pages + transcript details
test/
  widget_test.dart             boot smoke test
  flow_test.dart               sign-in → dashboard → chat → history
```

## iOS setup still pending (before TestFlight)

In Xcode (Runner → Signing & Capabilities): development team, Push
Notifications, Background Modes (fetch + remote notifications), Associated
Domains (`applinks:auth.jbhomebase.app`). APNs needs a real device and the
`.p8` key uploaded to Firebase. App icon + splash are placeholders.

## Locked decisions

- Bundle ID: `com.jbhomebase.app` · Display name: JB Homebase
- Accent: cobalt (`#3157F6`)
- iOS only for v1 · Voice format: M4A
- Passkey primary, magic link recovery; if `passkeys` breaks on iOS,
  ship magic-link-only for cutover
