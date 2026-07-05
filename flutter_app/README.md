# JB Homebase — Flutter app (iOS)

Thin client over the FastAPI gateway. Replaces Telegram as the primary
channel. v1 is iOS-only. Android is deferred.

Design direction lives in `../docs/flutter-design/` (JB Homebase prototype)
and the PRD in `../docs/plans/flutter-app-prd.md`. Architecture decisions in
`../docs/plans/flutter-architecture.md` (note: the IA there predates the
JB Homebase design pivot — this README is current).

## Status

- iOS platform scaffold generated; builds and runs on the simulator.
- All data is mock (`lib/shared/api/mock_data.dart`); `api_client.dart` is a
  no-op shell. Real HTTP, streaming, auth, voice capture, and push land in
  PR2 — search the repo for `TODO(backend)` for the exact integration points.
- `dart analyze --fatal-infos` clean; widget + flow tests pass
  (`flutter test`).

## The app

Passkey sign-in (tap-through mock) → three-tab shell with a floating pill
nav (NavigationRail on ≥ 840dp):

- **Home** — eyebrow date, Playfair greeting, Daily Digest gradient card
  (the one loud moment), horizontal agent dock, week stripe + sparkline.
- **Agents** — agent picker chips (Claw Main, Workout Coach), asymmetric
  chat bubbles, per-agent tinted typing indicator, tool-call chips,
  composer with mic (voice overlay) + send. Threads are per-agent Riverpod
  families and survive tab switches.
- **Insights** — week stripe + animated sparkline cards; grows into the
  PostHog-fed analytics view.

Voice: mic in the chat composer → recording overlay (animated waveform) →
transcript preview → Send appends to the active agent's thread.

## Design system

- Palette: warm cream `#F6F1E7` bg, deep slate `#1B222B` ink, sage
  `#64805F`/`#9CB39A` as the single accent. Dark mode follows the system.
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

## File map

```
lib/
  main.dart                    app entry, ProviderScope
  app.dart                     MaterialApp.router, light/dark theme
  theme/                       colors, typography, app_theme, spacing, motion
  routing/
    app_router.dart            GoRouter: auth redirect + StatefulShellRoute
    routes.dart                /home /agents /insights /voice /auth/*
  shell/homebase_shell.dart    floating pill nav / NavigationRail
  features/
    home/                      dashboard (digest, agent dock, previews)
    chat/                      chat screen + typing indicator, tool chips
    insights/                  insights screen
    auth/                      passkey + magic link
    voice/                     capture overlay + preview
  shared/
    models/                    Agent, Message
    widgets/                   BouncyButton, FadeSlideIn, WeekStripe,
                               SparklineCard, Entrance
    api/                       api_client (stub), mock_data
  state/app_state.dart         Riverpod: auth, active agent, threads, typing
test/
  widget_test.dart             boot smoke test
  flow_test.dart               sign-in → dashboard → chat → insights
```

## iOS setup still pending (before TestFlight)

In Xcode (Runner → Signing & Capabilities): development team, Push
Notifications, Background Modes (fetch + remote notifications), Associated
Domains (`applinks:auth.jbhomebase.app`). APNs needs a real device and the
`.p8` key uploaded to Firebase. App icon + splash are placeholders.

## Locked decisions

- Bundle ID: `com.jbhomebase.app` · Display name: JB Homebase
- Accent: sage (`#64805F` light / `#9CB39A` dark)
- iOS only for v1 · Voice format: M4A
- Passkey primary, magic link recovery; if `passkeys` breaks on iOS,
  ship magic-link-only for cutover
