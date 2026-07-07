# Jordan Claw Flutter App — Architecture Decisions

> **PARTIALLY STALE.** The design/IA/theming sections (Granola-style Today/
> Room/Drawer, system fonts, light-only) were superseded by the JB Homebase
> design pivot (July 2026) — trust the code in `flutter_app/lib/` and
> `docs/flutter-design/`. The LOCKED technical decisions (Riverpod, go_router,
> http-not-Dio, bundle id, voice format, auth fallback) and the backend-wiring
> roadmap remain authoritative — flag any deviation to Jordan before building.

Investigation phase for the Flutter scaffold. Decisions are opinionated singletons. Where confidence is low, it is called out plainly. Date of research: May 2026.

## Summary table

| Concern | Choice | Why |
|---|---|---|
| Flutter SDK | 3.44.0 (Dart 3.12) stable | Latest stable as of mid-May 2026; widget preview perf improvements and Impeller Vulkan/SDF upgrades land here. |
| State | Riverpod 3.0 (with `riverpod_generator`) | Compile-time safe, no `BuildContext` dependency, async providers fit a server-truth client, `ProviderContainer.test` makes ViewModels trivially testable. |
| Routing | `go_router` (`StatefulShellRoute.indexedStack`) | Maintained by the Flutter team. First-class deep linking for the FCM tap path. Shell route keeps the drawer + bottom action bar stable across surfaces. Tablet-safe because branches own their own nav stacks. |
| HTTP | `http` (official) | Thin client, no agent logic. We don't need Dio's interceptors/retry/FormData since the gateway already centralizes that. Smaller bundle, fewer surprises. |
| Streaming | `http.Client().send()` over `StreamedResponse` + a tiny `EventStreamDecoder` we own | Works for both SSE (`text/event-stream`) and chunked HTTP. No package lock-in. Backend can pick later without a client rewrite. |
| Auth | `passkeys` (Corbado) for WebAuthn + `app_links` for magic-link universal links + `flutter_secure_storage` for the session token | `passkeys` is the only credible cross-platform option; covers iOS ASAuthorization. Magic link is a universal-link tap that POSTs the signed token. |
| Voice | `record` (capture, M4A/AAC) + `audio_waveforms` (visualization) + `http.MultipartRequest` (upload) + `permission_handler` (runtime perms) | `record` is the most maintained recorder. `audio_waveforms` handles real-time amplitude rendering. Multipart goes straight through `http` so we don't add Dio just for uploads. |
| Push | `firebase_messaging` + `flutter_local_notifications` | FCM is the assumed default. `flutter_local_notifications` is needed to render foreground notifications on iOS and to handle tap actions consistently. |
| Theming | Material 3 (`useMaterial3: true`) with a custom `ColorScheme.fromSeed` + a thin `AppTheme` wrapper on top | M3 is the Flutter default in 2026. Seeded color scheme gets us most of Granola for free. We override `cardTheme`, `textTheme`, and `scaffoldBackgroundColor` for the warm off-white + 14pt radius. |

## Locked decisions

Confirmed by Jordan on 2026-05-22. These override anything inferred from earlier research.

| Decision | Value |
|---|---|
| Accent color | `#6B7A3F` (warm moss, slight yellow lean) |
| State management | Riverpod 3.0 with `riverpod_generator` (codegen approach) |
| Bundle identifier | `com.jbhomebase.app` (namespace matches the `jb_homebase` repo, not the product name) |
| App display name | "Jordan Claw" (product name; bundle uses jbhomebase) |
| Auth hostname | `auth.jbhomebase.app` (placeholder, may change before backend wiring) |
| Platform scope | iOS only for v1. Android setup deferred. |
| Voice file format | M4A (record package default, AAC codec) — Whisper accepts it directly |
| App icon + splash | Placeholders for scaffold; final assets before TestFlight |
| Passkey cutover policy | If `passkeys` package breaks on iOS, fall back to magic-link-only and revisit passkeys post-cutover |

## Build environment constraint

The scaffold is hand-written Dart on Linux. Flutter SDK is not installed on the Linux box. Implications:

- No `flutter create` was run. The repo contains `lib/`, `test/`, `pubspec.yaml`, `analysis_options.yaml`, and `README.md` only.
- No `ios/`, `android/`, `macos/`, `linux/`, `windows/`, or `web/` directories exist yet. Those are generated on a Mac via `flutter create . --platforms=ios --org=app.jbhomebase --project-name=jb_homebase_app`.
- No `*.g.dart` files exist yet. Riverpod codegen requires `dart run build_runner build` on a machine with the Flutter SDK. The `part 'foo.g.dart';` directives in our source will resolve once codegen runs.
- iOS platform setup (signing, entitlements, AASA, APNs key, Info.plist mic description) happens on the Mac.
- All Dart code in the scaffold is syntactically valid in isolation. The only "broken" references are the codegen `part` directives, which are expected and documented in the README.

## 1. Flutter SDK + tooling

- **Flutter:** 3.44.0 (stable channel, May 2026). Released around Google I/O 2026.
- **Dart:** 3.12.x. Use `from __future__`-equivalent: Dart 3 patterns (records, switch expressions, sealed classes) are now table stakes.
- **Install:** `fvm` is recommended so this repo pins exactly `3.44.0` (committed `.fvmrc`). Avoids "works on Jordan's machine" drift across phone, laptop, iPad dev sessions.
- **2026 features worth using:**
  - Widget Preview environment (`@Preview()`) — memory usage cut ~50% in 3.44 ([Flutter 3.44 release notes](https://docs.flutter.dev/release/release-notes/release-notes-3.44.0)). Use it for cards and chat bubbles in `shared/widgets/`.
  - Impeller Vulkan + SDF circles — relevant for the recording-overlay waveform and rounded avatar chips; we get cleaner rendering for free.
  - Switch expressions + sealed classes for `Card` discriminated unions (morning briefing vs weekly review vs eval-regression alert).
- **Tooling baseline:**
  - `dart format` (page_width 100, trailing_commas: preserve)
  - `dart analyze --fatal-infos` (CI gate)
  - `flutter_lints` as the base ruleset, plus `strict-casts: true`, `strict-inference: true`, `strict-raw-types: true`. (Cite: `dart-run-static-analysis` skill, "Comprehensive `analysis_options.yaml`".)

Sources: [Flutter 3.44 release notes](https://docs.flutter.dev/release/release-notes/release-notes-3.44.0), [What's new in Flutter 3.44](https://blog.flutter.dev/whats-new-in-flutter-3-44-b0cc1ad3c527), [Dart changelog](https://dart.dev/changelog).

## 2. State management

| Candidate | Verdict |
|---|---|
| **Riverpod 3.0** | Chosen. Async providers (`FutureProvider`, `StreamProvider`) map cleanly onto server-truth: each provider re-reads from the gateway. Code generation catches the dependency graph at compile time. `ProviderContainer.test` removes the boilerplate from ViewModel tests. ([Riverpod 3.0 release](https://riverpod.dev/docs/whats_new)) |
| Bloc | Heavier event/state ceremony than this client needs. Best when you need an audit trail of state transitions — we don't, the server has that. Would force us to write 3x the boilerplate for chat streaming. |
| Provider | Effectively superseded by Riverpod for new projects. Same author. No reason to start here in 2026. |

**Recommendation:** Riverpod 3.0 with `riverpod_generator` + `flutter_riverpod` + `riverpod_annotation`. Skip `hooks_riverpod` — we don't need `flutter_hooks` for v1; we can revisit if widget code gets tangled.

**How it pairs with the MVVM-style layering the `flutter-apply-architecture-best-practices` skill recommends:** ViewModels become `@riverpod class` (Notifier) classes. Repositories are plain Dart classes exposed through a `@riverpod` provider. The skill's "inject repository via constructor" rule still holds, just via `ref.read(repoProvider)` inside the notifier.

Sources: [Riverpod 3.0 docs](https://riverpod.dev/docs/whats_new), [Flutter State Management in 2026](https://samioda.com/en/blog/flutter-state-management-2026), [BLoC vs Riverpod in 2026](https://flutterstudio.dev/blog/bloc-vs-riverpod.html).

## 3. Routing

| Candidate | Verdict |
|---|---|
| **go_router** | Chosen. Officially recommended by the Flutter team. First-class deep linking from FCM and universal links. `StatefulShellRoute` keeps Today and Room as parallel branches with independent nav stacks. ([Flutter docs — Deep linking](https://docs.flutter.dev/ui/navigation/deep-linking)) |
| Navigator 2.0 (raw) | Too much boilerplate for the router delegate and route information parser. We'd be reinventing go_router. |
| auto_route | Code-gen heavy. More opinionated. Smaller ecosystem. No advantage over go_router for our route surface. |

**Recommendation:** `go_router` with a single `StatefulShellRoute.indexedStack` for `Today` + `Room(claw-main)`. Drawer is a modal route, not a branch. Deep link paths:

```
/today
/today/card/:cardId
/room/claw-main
/room/claw-main/conversation/:conversationId
/voice/capture        (modal)
/auth/passkey
/auth/magic-link?token=...
```

The FCM tap handler reads `RemoteMessage.data['deep_link']` and calls `_router.go(path)`. Magic-link handler reads `app_links.uriLinkStream` and does the same. (Cite: `flutter-setup-declarative-routing` skill, "Programmatic Navigation" example.)

Tablet safety: we use `LayoutBuilder` only at the shell level; routes themselves don't assume phone widths. The bottom action bar floats inside the shell, not in any single page.

Sources: [Flutter Deep Linking guide](https://codewithandrea.com/articles/flutter-deep-links/), [go_router docs](https://docs.flutter.dev/ui/navigation), [Routing Best Practices in Flutter](https://verygood.ventures/blog/routing-best-practices-in-flutter/).

## 4. HTTP + streaming

**REST:** `http` (Dart team). Reasoning:

- Thin client. We are not adding interceptors, request cancellation, or retry policy in the app — the gateway owns retry/idempotency.
- ~30–50 KB vs ~200–350 KB for Dio. ([Dio vs http in Flutter](https://medium.com/@bouargalne.hamid/dio-vs-http-in-flutter-825908189cf0))
- `MultipartRequest` is fine for the voice upload. Yes, Dio's `FormData` + `onSendProgress` is nicer, but we can wire progress with `http.MultipartRequest.send()` returning a `StreamedResponse` and reading bytes-sent off the request body stream if/when progress UI is needed (post-v1).

(Cite: `flutter-use-http-package` skill, "Configuration & Permissions" — iOS network access is on by default; no extra entitlements needed for the gateway.)

**Streaming (the load-bearing decision):** Backend has not committed to SSE vs chunked HTTP. Pick a client approach that supports both without a rewrite.

**Recommendation:** Use `http.Client().send(request)` to get a `StreamedResponse`, then run `response.stream.transform(utf8.decoder).transform(const LineSplitter())` and parse line-by-line. We own a small `EventStreamDecoder` class with two methods:

```dart
Stream<AgentEvent> decodeSse(Stream<String> lines);     // text/event-stream
Stream<AgentEvent> decodeNdjson(Stream<String> lines);  // chunked HTTP, newline-delimited JSON
```

The choice between them is one branch on `response.headers['content-type']`. No package dependency. Swapping in `dio` later only requires changing the transport, not the decoder.

We explicitly **reject** `flutter_http_sse`, `sse.dart`, and similar. They lock us into SSE and add maintenance risk for a 60-line decoder we can own.

Sources: [Top Flutter SSE packages — Flutter Gems](https://fluttergems.dev/server-sent-events/), [Flutter SSE Streaming AI responses (2026)](https://aliwajdan.medium.com/flutter-sse-streaming-how-i-built-real-time-ai-responses-in-flutter-ffd1c32d0380), [Dio vs http practical comparison](https://dev.to/heyroziq/dio-vs-http-in-flutter-a-practical-clear-comparison-2id8).

## 5. Auth (passkey + magic link)

This is the highest-uncertainty item. Be honest:

**State of WebAuthn/passkeys on Flutter in May 2026:**

- The `passkeys` package (by Corbado) is the only credible Dart wrapper. It exposes iOS `ASAuthorization` (passkey APIs) through a small Dart surface. ([passkeys on pub.dev](https://pub.dev/packages/passkeys))
- The `flutter-passkeys` repo has had patchy maintenance — one of the search results flagged a recent build issue. Risk is real but manageable: the package surface is small enough to fork if needed.
- No official Flutter team package exists for WebAuthn as of May 2026.

**Recommendation:** Use the `passkeys` package for the WebAuthn flow on iOS. Server side, the FastAPI gateway acts as the relying party — we are not using Corbado's hosted RP. Token storage goes in `flutter_secure_storage` (iOS Keychain).

**Locked fallback policy:** If `passkeys` breaks on iOS, ship magic-link-only and revisit passkeys post-cutover. Do NOT block cutover on passkey perfection. The magic-link path is always available behind the "Having trouble?" link the PRD specifies.

**Magic link is just URL handling.** Use `app_links` for iOS universal links. Setup (executed on Mac when iOS scaffold is generated):

- `applinks:auth.jbhomebase.app` in `Runner.entitlements`.
- Host the AASA file at `https://auth.jbhomebase.app/.well-known/apple-app-site-association`.
- Set `FlutterDeepLinkingEnabled` to `NO` in `Info.plist` so `app_links` owns the tap.
- AASA propagation can take up to 24h after the first publish. ([app_links pub.dev](https://pub.dev/packages/app_links))

Android setup deferred — iOS-only v1.

(Cite: `flutter-setup-declarative-routing` skill, "Workflow: Configuring Platform Deep Linking".)

**Known gaps to flag:**

- Passkey registration requires the device to support a screen lock. Jordan's iPhone is fine.
- Cross-device passkey sync depends on iCloud Keychain. Register passkeys explicitly on phone, laptop, and iPad during onboarding rather than relying on sync. PRD already says this.

Sources: [passkeys package](https://pub.dev/packages/passkeys), [Corbado flutter-passkeys repo](https://github.com/corbado/flutter-passkeys), [app_links package](https://pub.dev/packages/app_links), [Flutter universal links cookbook](https://docs.flutter.dev/cookbook/navigation/set-up-universal-links).

## 6. Voice recording

**Packages:**

- `record` — capture audio to file (M4A/AAC, locked format). Most maintained recorder on pub.dev. ([record on pub.dev](https://pub.dev/packages/record))
- `audio_waveforms` — real-time amplitude visualization during recording, plus waveform playback. Required for the Granola-style recording overlay in the PRD. ([audio_waveforms on pub.dev](https://pub.dev/packages/audio_waveforms))
- `permission_handler` — runtime microphone permission. Standard, no surprises.
- `path_provider` — temp directory for the audio file before upload.
- `http.MultipartRequest` — upload audio + transcript in a single request. No new dependency.

**Rejected:** `flutter_sound` is a heavier all-in-one. `audio_waveform_recorder` bundles both behaviors but the recorder is less flexible than `record`.

**iOS Info.plist (`ios/Runner/Info.plist`, added on Mac after `flutter create`):**

```xml
<key>NSMicrophoneUsageDescription</key>
<string>Jordan Claw records voice dumps and transcribes them server-side.</string>
```

Plus a runtime request via `permission_handler` before the first recording. Android setup deferred — iOS-only v1.

**Upload pattern:** After stop, server-side Whisper runs already (per PRD — existing delivery-coach pipeline). The app POSTs `multipart/form-data` with `audio` (binary, M4A), `room_id`, and optional `client_transcript` if we ever do client-side transcription (we won't in v1).

Sources: [record package](https://pub.dev/packages/record), [audio_waveforms package](https://pub.dev/packages/audio_waveforms), [Flutter audio recording cookbook](https://docs.flutter.dev/cookbook/audio/record).

## 7. Push notifications

**Package:** `firebase_messaging` + `flutter_local_notifications`.

`firebase_messaging` handles FCM tokens, APNs token registration, and background message receipt. `flutter_local_notifications` is required because:
- iOS does not show foreground notifications without manual presentation.
- Tap actions on foreground notifications need a unified handler across platforms.

**iOS-specific APNs setup (executed on Mac after `flutter create`):**

1. Apple Developer Portal → Keys → create an APNs Auth Key (`.p8` file). Prefer auth key over certificate — auth keys don't expire and work across all your bundle IDs. ([FCM via APNs Integration](https://firebase.flutter.dev/docs/messaging/apple-integration/))
2. Firebase Console → Project Settings → Cloud Messaging → upload `.p8`, fill in Key ID and Team ID.
3. Xcode → Runner → Signing & Capabilities → add **Push Notifications**.
4. Xcode → Runner → Signing & Capabilities → **Background Modes** → enable both **Background fetch** and **Remote notifications**.
5. `Info.plist`: add `FirebaseAppDelegateProxyEnabled = NO` only if we want to handle APNs manually. For v1, leave default (proxy enabled) — simpler.
6. **No Notification Service Extension required for v1.** The PRD doesn't need rich media (images, attachments). If we add rich notifications in v1.1, add an NSE target then.
7. **APNs does not work on iOS Simulator.** Real device required for E2E testing. The scaffold will run on the simulator with FCM stubbed.

Android setup deferred — iOS-only v1.

**Deep link from notification:** Handle via `FirebaseMessaging.instance.getInitialMessage()` (cold start) + `FirebaseMessaging.onMessageOpenedApp.listen()` (warm start). Read `message.data['deep_link']`, call `_router.go(path)`.

Sources: [FlutterFire FCM Apple integration](https://firebase.flutter.dev/docs/messaging/apple-integration/), [FCM Flutter client docs](https://firebase.google.com/docs/cloud-messaging/flutter/client), [FlutterFire Notifications](https://firebase.flutter.dev/docs/messaging/notifications/).

## 8. Theming + design tokens

**Approach:** Material 3 with a custom seeded `ColorScheme` and targeted component overrides. Not custom from scratch.

Reasoning: M3 is the Flutter default in 2026 ([Mastering Material 3 in Flutter](https://www.christianfindlay.com/blog/flutter-mastering-material-design3)), gives us `Card`, `FilledButton`, `NavigationBar`, ripple, focus states, semantic colors, type scale for free. Granola's visual direction is achievable inside M3 by overriding the seed color, `cardTheme`, and `scaffoldBackgroundColor`. Rolling our own would mean re-implementing focus rings, splash, ink, and a11y semantics for negligible gain.

**Concrete tokens (these go directly into `lib/theme/app_theme.dart`):**

```dart
// Background — warm off-white, picked from PRD direction
static const background      = Color(0xFFF7F5F0);
static const surface         = Color(0xFFFFFFFF); // cards sit on a barely-brighter surface
static const surfaceVariant  = Color(0xFFEFEDE6); // subtle differentiation for chips
static const onSurface       = Color(0xFF1A1A1A); // near-black text
static const onSurfaceMuted  = Color(0xFF6B6B6B); // captions, metadata

// Accent — custom Jordan Claw hue, sampled in the Granola olive direction
// Slightly more saturated and warmer than Granola's green so it doesn't feel borrowed.
// HSL ≈ (78, 38%, 38%) — deep moss with a yellow lean.
static const accent          = Color(0xFF6B7A3F);
static const accentOnPrimary = Color(0xFFFFFFFF);

// Status (used sparingly: eval regression alert, rating drop)
static const warning         = Color(0xFFB8860B); // dark goldenrod, not orange
static const error           = Color(0xFFB04444); // muted brick, not bright red
```

**Type scale:** Use M3's default text theme (`Typography.englishLike2021`), then override only the families to system fonts (SF on iOS — Flutter's default). Bump `bodyLarge` line height to 1.5 to match the PRD's generous-line-height requirement. Customize `displaySmall` and `titleLarge` to use weight 600 instead of 400 for stronger visual hierarchy.

**Spacing scale (adopt PRD as-is):**

```dart
class Spacing {
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 16.0;
  static const xl = 24.0;
  static const xxl = 32.0;
}
```

**Card radius:** **14pt** (split the PRD's 12–16 range). Rounded enough to feel warm, not so rounded it reads as cartoon.

```dart
cardTheme: CardTheme(
  elevation: 0,                          // no Material elevation — use subtle shadow only
  shape: RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(14),
  ),
  color: surface,
  margin: EdgeInsets.zero,
  shadowColor: const Color(0x14000000),  // 8% black, very subtle
)
```

**Light theme only in v1.** Dark mode is v1.1 (per PRD scaffolding prompt). Define `AppTheme.light` now; structure `AppTheme.dark` as a stub returning the light theme so we can swap in v1.1 without API churn.

Sources: [Material 3 in Flutter](https://m3.material.io/develop/flutter), [Mastering Material 3 — Christian Findlay](https://www.christianfindlay.com/blog/flutter-mastering-material-design3), [Flutter themes cookbook](https://docs.flutter.dev/cookbook/design/themes).

## Cross-cutting decisions

### Project layout

Hybrid: features-by-folder for UI, types-by-folder for data. Adapted from the `flutter-apply-architecture-best-practices` skill's "Project Structure" section.

```
flutter_app/lib/
├── main.dart
├── app.dart                          # MaterialApp.router + theme + ProviderScope
├── theme/
│   ├── app_theme.dart                # AppTheme.light, design tokens
│   ├── colors.dart
│   ├── spacing.dart
│   └── typography.dart
├── routing/
│   ├── app_router.dart               # GoRouter config
│   └── routes.dart                   # route name constants
├── data/
│   ├── models/                       # API DTOs (TodayCard, Conversation, Message, Room)
│   ├── repositories/                 # TodayRepository, RoomRepository, AuthRepository
│   └── services/
│       ├── api_client.dart           # http.Client wrapper
│       ├── event_stream_decoder.dart # SSE + NDJSON decoder
│       └── secure_storage.dart       # flutter_secure_storage wrapper
├── features/
│   ├── today/
│   │   ├── view/
│   │   └── view_model/               # @riverpod notifier
│   ├── room/
│   │   ├── view/
│   │   └── view_model/
│   ├── voice/
│   ├── auth/
│   └── drawer/
└── shared/
    └── widgets/                       # AppCard, AppChip, ToolCallChip, BottomActionBar
```

(Cite: `flutter-apply-architecture-best-practices` skill, "Project Structure" — "group UI components by feature, and group Data/Domain components by type".)

### JSON serialization

Manual `fromJson`/`toJson` with switch-based type guards. No `json_serializable` for v1. Reasoning: the model surface is small (Card, Message, Conversation, Room, ContextItem). Hand-rolled serialization avoids the `build_runner` ceremony and keeps the diff small. Revisit if we cross ~20 models. (Cite: `flutter-implement-json-serialization` skill, "High-Fidelity Model Implementation".)

Large payloads (e.g., History tab loading 100+ conversations) go through `compute(parseList, response.body)` to keep the main isolate jank-free.

### Testing baseline

- `package:flutter_test` for widget tests
- `package:test` for pure Dart unit tests
- `mockito` with `@GenerateNiceMocks` for `ApiClient` and repository mocks
- Folder layout mirrors `lib/` — `test/data/repositories/today_repository_test.dart` etc.
- Riverpod 3.0's `ProviderContainer.test()` for ViewModel tests
- Initial coverage target: repositories + ViewModels at 70%+. UI smoke tests for each route. Not chasing 100%.

(Cite: `dart-add-unit-test` skill, "Structuring Test Files" and "Mocking with Mockito".)

### Linting config

`flutter_app/analysis_options.yaml`:

```yaml
include: package:flutter_lints/flutter.yaml

analyzer:
  exclude:
    - "**/*.g.dart"
    - "**/*.freezed.dart"
    - "lib/generated/**"
  language:
    strict-casts: true
    strict-inference: true
    strict-raw-types: true
  errors:
    invalid_assignment: warning
    missing_return: error
    todo: ignore

linter:
  rules:
    avoid_print: true
    prefer_const_constructors: true
    prefer_const_literals_to_create_immutables: true
    require_trailing_commas: true
    use_super_parameters: true

formatter:
  page_width: 100
  trailing_commas: preserve
```

CI runs `dart format --output=none --set-exit-if-changed .` and `dart analyze --fatal-infos`. (Cite: `dart-run-static-analysis` skill, "Comprehensive `analysis_options.yaml`".)

## Package list (for pubspec.yaml)

Routing + state:
- `flutter_riverpod ^3.0.0` — state management, async providers, testable containers
- `riverpod_annotation ^3.0.0` — annotations for code-gen
- `go_router ^15.0.0` — declarative routing, deep links, shell routes

HTTP:
- `http ^1.3.0` — REST client, also handles multipart and streaming via `Client.send()`

Storage:
- `flutter_secure_storage ^10.0.0` — session token in iOS Keychain
- `path_provider ^2.1.0` — temp directory for audio files before upload

Auth + links:
- `passkeys ^2.0.0` — WebAuthn / FIDO2 on iOS (Corbado, monitor for maintenance)
- `app_links ^7.0.0` — universal links for magic-link tap and notification deep link

Voice:
- `record ^6.0.0` — microphone capture to file
- `audio_waveforms ^2.0.0` — real-time waveform visualization
- `permission_handler ^12.0.0` — runtime microphone + notification permissions

Push:
- `firebase_core ^4.0.0` — FCM prerequisite
- `firebase_messaging ^17.0.0` — FCM token, APNs registration, message handlers
- `flutter_local_notifications ^20.0.0` — foreground notification presentation + tap handling

Dev:
- `flutter_lints ^7.0.0` — base lint ruleset
- `build_runner ^2.4.0` — code-gen for riverpod_generator
- `riverpod_generator ^3.0.0` — code-gen for `@riverpod` providers
- `mockito ^5.5.0` — mocks for unit tests

Versions are conservative ranges; pin exact at lock time. **All except `passkeys` are well-maintained**. `passkeys` is the package to monitor.

## Open questions for Jordan

1. **Apple Team ID.** Bundle ID is locked to `com.jbhomebase.app`. The Apple Developer Team ID is still needed for AASA, APNs key configuration, and `passkeys` relying-party setup. Capture when the Mac/Xcode setup happens.
2. **Final auth hostname.** Locked to `auth.jbhomebase.app` for now. Confirm before AASA publish, since propagation takes 24h.

## Risks

- **`passkeys` package maintenance (medium).** Recent maintenance gaps observed. Mitigation: keep the auth layer behind a thin `AuthRepository` interface so we can swap implementations or fork the package without UI changes.
- **APNs requires real device (low, expected).** iOS Simulator cannot receive push. The scaffold runs fine on simulator; push E2E testing needs Jordan's iPhone.
- **AASA propagation lag (low, time-bound).** Up to 24h after first host. Schedule the magic-link hostname publish at least a day before the first end-to-end test.
- **Streaming format unknown (low, by design).** We are hedging with a transport-agnostic `EventStreamDecoder`. Worst case: a one-day swap when the backend lands.
- **Flutter 3.44 breaking changes (low).** Material 3 has been default for a while; no major breaks expected. Pin SDK version via `fvm` to avoid drift.
- **Code-gen friction (low).** `build_runner` watcher consumes a terminal during dev. Standard Flutter pain; not a blocker.
- **Flutter SDK not installed locally (medium, time-bound).** Scaffold is hand-written Dart. iOS platform files, `pub get`, and `build_runner` codegen run on a Mac. Mitigation: README documents the Mac-finish steps in order.
