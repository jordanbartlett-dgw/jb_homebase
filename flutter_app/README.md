# JB Homebase — Flutter app (iOS)

Thin client over the FastAPI gateway and the primary user channel. v1 is
iOS-only. Android is deferred.

Design direction lives in `../docs/flutter-design/` (JB Homebase prototype)
and the PRD in `../docs/plans/flutter-app-prd.md`. Architecture decisions in
`../docs/plans/flutter-architecture.md` (note: the IA there predates the
JB Homebase design pivot — this README is current).

## Status

- **Text chat for Claw Main, Workout Coach, and Med Check; conversation
  history; Daily Digest; and Calendar are live
  gateway surfaces**: sends go to
  `POST /app/messages` with bearer `CLAW_APP_TOKEN` auth and one idempotency
  key per message; active threads hydrate after relaunch. History lists
  retained sessions, opens read-only transcripts, and New Chat archives the
  current session before the next send. Home reads `GET /app/today` for the
  existing morning briefing and structured seven-day Fastmail agenda; refresh
  re-fetches without rerunning the agent. Voice capture is live: the app
  records M4A, transcribes without sending, allows transcript/audio review,
  then sends the edited draft through the classifier-selected agent.
- Still pending: passkey/magic-link screens (live builds skip them — the
  static token is the interim auth) and push delivery.
- `dart analyze --fatal-infos` clean; unit + widget + flow tests pass
  (`flutter test`); on-simulator integration test drives the live path
  (`integration_test/live_chat_test.dart`).

## The app

Passkey sign-in (tap-through mock) → three-tab shell with a floating pill
nav (NavigationRail on ≥ 840dp):

- **Home** — real Daily Digest preview, upcoming Fastmail events, pull-to-
  refresh, and horizontal agent dock. Digest opens into a full selectable
  briefing; Calendar opens a grouped seven-day agenda with an Ask Claw action.
- **Agents** — agent picker chips (Claw Main, Workout Coach, Med Check), asymmetric
  chat bubbles, per-agent tinted typing indicator, tool-call chips,
  composer with mic (voice overlay) + send, and New Chat. Threads are
  per-agent Riverpod families, survive tab switches, and hydrate from the
  gateway after relaunch. Med Check adds a decision-support boundary and
  editable starter prompts; Markdown source links open in the system browser.
- **History** — retained app sessions grouped by date with agent identity,
  active-session state, cursor pagination, and read-only transcripts.

Voice: mic in the chat composer → real M4A recording with live amplitude →
server-side Whisper draft → editable transcript and audio playback → Send
routes the reviewed text and opens the classifier-selected agent's thread.

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

The live-path integration test covers text and voice against the committed
local stub, avoiding test conversations in production:

```bash
# terminal 1
dart run tool/local_gateway_stub.dart

# terminal 2 (simulator)
flutter test integration_test/live_chat_test.dart -d "iPhone 17" \
  --dart-define=GATEWAY_URL=http://127.0.0.1:8787 \
  --dart-define=CLAW_APP_TOKEN=stub-token
```

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
                               + digest/calendar detail screens
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
  state/today_state.dart       Riverpod: briefing/calendar loading + refresh
test/
  widget_test.dart             boot smoke test
  flow_test.dart               sign-in → dashboard → chat → history
```

## iOS setup still pending (before TestFlight)

In Xcode (Runner → Signing & Capabilities): development team, Push
Notifications, Background Modes (fetch + remote notifications), Associated
Domains (`applinks:auth.jbhomebase.app`). APNs needs a real device and the
`.p8` key uploaded to Firebase. Splash is still a placeholder.

## Locked decisions

- Bundle ID: `com.jbhomebase.app` · Display name: JB Homebase
- Accent: cobalt (`#3157F6`)
- iOS only for v1 · Voice format: M4A
- Passkey primary, magic link recovery; if `passkeys` breaks on iOS,
  ship magic-link-only for cutover
