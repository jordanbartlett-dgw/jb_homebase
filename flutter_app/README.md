# Jordan Claw — Flutter app (iOS)

Thin client over the FastAPI gateway. Replaces Telegram as the primary channel.
v1 is iOS-only. Android is deferred.

This directory is a hand-written Dart scaffold. The Flutter SDK is not
installed on the Linux dev box, so:

- No `flutter create` was run.
- No `ios/`, `android/`, `macos/`, `linux/`, `windows/`, or `web/` directories exist.
- No `*.g.dart` files exist. Riverpod codegen runs on the Mac.
- iOS platform setup (signing, entitlements, AASA, APNs, mic Info.plist) happens on the Mac.

## What this is

- All three v1 surfaces (Today, Drawer, Room with Chat/Context/History tabs) wired with mock data.
- Voice capture overlay + preview (UI only — no audio capture yet). The
  waveform and timer animate; real amplitude data lands in PR2.
- Passkey + magic-link auth screens that tap-through to a signed-in state via Riverpod.
- Granola-style theme: warm off-white `#F7F5F0`, accent `#6B7A3F` warm moss, 14pt card radius.
- Motion system: `theme/motion.dart` tokens drive every animation. Press
  feedback is scale + haptic (`Pressable`), not ink ripple; ripple is
  disabled globally for an iOS feel. Lists cascade in via `Entrance`.
- Chat simulates a typing indicator + canned assistant ack after each send
  so the loop demos end-to-end; PR2 replaces it with gateway streaming.

## What is stubbed

- All data is hardcoded in `lib/shared/api/mock_data.dart`.
- `lib/shared/api/api_client.dart` is a no-op shell. Real HTTP and streaming wire in PR2.
- No real audio capture, no real Whisper upload, no real auth, no real push notifications.
- TODOs in code mark each backend integration point.

## Mac-finish steps

These run once on a Mac with Flutter installed.

1. Install Flutter SDK (recommended: `fvm install 3.44.0 && fvm use 3.44.0`).
2. `cd flutter_app/`
3. Generate the iOS platform scaffold without touching `lib/`:
   ```bash
   flutter create . --platforms=ios --org=app.jbhomebase --project-name=jb_homebase_app
   ```
   This creates `ios/` and seeds platform files. The existing `lib/` is preserved.
4. `flutter pub get`
5. Run Riverpod codegen so `*.g.dart` files exist:
   ```bash
   dart run build_runner build --delete-conflicting-outputs
   ```
6. Open `ios/Runner.xcworkspace` in Xcode. In **Signing & Capabilities**:
   - Set bundle identifier to `com.jbhomebase.app`.
   - Set the development team.
   - Add capability **Push Notifications**.
   - Add capability **Background Modes** with **Background fetch** and **Remote notifications** enabled.
   - Add capability **Associated Domains** with `applinks:auth.jbhomebase.app`.
7. Edit `ios/Runner/Info.plist`. Add:
   ```xml
   <key>NSMicrophoneUsageDescription</key>
   <string>Jordan Claw records voice dumps and transcribes them server-side.</string>
   <key>FlutterDeepLinkingEnabled</key>
   <false/>
   ```
8. Run on the simulator:
   ```bash
   flutter run -d "iPhone 15"
   ```
   Push notifications require a real device. APNs does not work on the simulator.

## Where to navigate the running app

- Launch → Passkey screen → tap **Sign in with passkey** → Today.
- On Today: three cards (morning briefing, weekly review, low-rating alert).
- Bottom action bar: mic button (left), **Chat with Claw Main** CTA (center), pencil (right).
- Open the drawer (top-left icon) → tap **Claw Main**. Training and Jessie show **Coming soon**.
- Inside Claw Main: header + Chat / Context / History tabs.
  - Chat: mock conversation with an in-progress tool-call chip.
  - Context: 12 skills as chips; tap any chip to reveal its description.
  - History: 5 mock conversations grouped by Today / Yesterday / This week / Earlier.
- Tap the mic button anywhere → voice overlay → **Stop** → voice preview → **Send** returns to chat.
- Drawer → **Sign out** → back to passkey. Use **Having trouble?** to test the magic-link screen.

## File map

```
lib/
  main.dart                  app entry, ProviderScope
  app.dart                   MaterialApp.router + theme
  theme/
    app_theme.dart           ThemeData assembly, M3 + overrides
    colors.dart              palette tokens + layered shadow tokens
    typography.dart          M3 text theme, tracking + line-height tuned
    spacing.dart             4 / 8 / 12 / 16 / 24 / 32 scale
    motion.dart              duration + curve tokens for all animation
  routing/
    app_router.dart          GoRouter with auth redirect
    routes.dart              path constants
  features/
    today/                   Today screen + cards + model
    room/                    Room shell + Chat/Context/History tabs
    voice/                   capture overlay + preview
    auth/                    passkey + magic link
    drawer/                  Granola-style top-left drawer
  shared/
    widgets/                 AppCard, MicButton, BottomActionBar,
                             Pressable (press-scale + haptic),
                             Entrance (staggered fade-up)
    models/                  Room, Message, SkillInfo
    api/
      api_client.dart        stub, no real calls
      mock_data.dart         all hardcoded data lives here
  state/
    app_state.dart           Riverpod providers (codegen)
test/
  widget_test.dart           smoke test placeholder
pubspec.yaml
analysis_options.yaml
```

## Notes on Riverpod codegen

`lib/state/app_state.dart` uses `part 'app_state.g.dart';`. That file is
generated by `build_runner` and does not exist on Linux. Until you run
`dart run build_runner build` on the Mac, the file shows as missing —
that is expected and unblocks once codegen lands.

## TODOs left in code for backend wiring

Search the repo for `TODO(backend)`. The list:

- `api_client.dart`: today cards fetch, active conversation fetch, message send (streaming), voice multipart upload.
- `app_state.dart`: `appendUserMessage` should post to gateway and stream the assistant response.
- `main.dart`: Firebase init, push permission request, FCM token registration.
- `today_screen.dart`: pull-to-refresh is a `debugPrint` stub; card tap-to-expand is not implemented.
- `drawer/app_drawer.dart`: settings screen not built.
- `voice_overlay.dart`: real `record` capture; `audio_waveforms` live amplitude rendering.
- `voice_preview.dart`: multipart POST audio + transcript to `/api/rooms/:roomId/voice`.
- `passkey_screen.dart`: trigger Corbado `passkeys` flow, exchange with gateway, store token in `flutter_secure_storage`.
- `magic_link_screen.dart`: POST `/api/auth/magic-link`; consume `app_links` universal link on tap.
- `history_tab.dart`: continue-thread action should seed a new conversation server-side.

## Locked decisions for this scaffold

- Accent color: `#6B7A3F`
- Bundle ID: `com.jbhomebase.app`
- Auth host: `auth.jbhomebase.app`
- Display name: Jordan Claw
- Platforms: iOS only for v1
- Voice format: M4A (record default)
