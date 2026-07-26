import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:jb_homebase_app/app.dart';
import 'package:jb_homebase_app/features/chat/widgets/typing_indicator.dart';
import 'package:jb_homebase_app/features/voice/voice_capture.dart';
import 'package:jb_homebase_app/features/voice/voice_providers.dart';
import 'package:jb_homebase_app/shared/api/gateway_config.dart';

/// Drives the LIVE send path on a device/simulator against a gateway
/// reachable at GATEWAY_URL (in CI/dev: the local stub in scratchpad).
/// The stub must implement GET /app/today and
/// GET /app/conversations/current, POST /app/messages/stream,
/// POST /voice/transcribe, and POST /voice/messages.
///
/// Run:
///   flutter test integration_test -d `udid` \
///     --dart-define=GATEWAY_URL=http://127.0.0.1:8787 \
///     --dart-define=CLAW_APP_TOKEN=stub-token
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('live boot skips sign-in and a send round-trips the gateway', (tester) async {
    assert(GatewayConfig.isLive, 'run with GATEWAY_URL + CLAW_APP_TOKEN');

    await tester.pumpWidget(const ProviderScope(child: JBHomebaseApp()));
    await tester.pumpAndSettle();

    // Live mode boots straight to the dashboard — no passkey screen.
    expect(find.text('DAILY DIGEST'), findsOneWidget);

    // Dock → Claw Main chat. Content scrolls beneath the floating pill
    // nav, so lift the dock above it before tapping.
    await tester.drag(find.text('YOUR AGENTS'), const Offset(0, -150));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Claw Main'));
    await tester.pumpAndSettle();

    // Live threads start empty — no seeded mock messages.
    expect(find.textContaining('Pull the SAGE quotes'), findsNothing);

    await tester.enterText(find.byType(TextField).first, 'ping from integration test');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();
    expect(find.text('ping from integration test'), findsOneWidget);

    // The stub replies after ~1.5s; poll with fixed pumps (the typing
    // indicator animates forever, so pumpAndSettle would hang).
    var found = false;
    for (var i = 0; i < 80 && !found; i++) {
      await tester.pump(const Duration(milliseconds: 250));
      found = find.textContaining('stub reply for claw-main').evaluate().isNotEmpty;
    }
    expect(found, isTrue, reason: 'gateway reply should land in the thread');
    expect(find.byType(TypingIndicator), findsNothing);
    FocusManager.instance.primaryFocus?.unfocus();
    for (var i = 0; i < 8; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
  });

  testWidgets('voice capture previews before the reviewed transcript is sent', (tester) async {
    assert(GatewayConfig.isLive, 'run with GATEWAY_URL + CLAW_APP_TOKEN');
    final capture = _IntegrationVoiceCapture();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          voiceCaptureProvider.overrideWithValue(capture),
        ],
        child: const JBHomebaseApp(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.drag(find.text('YOUR AGENTS'), const Offset(0, -150));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Claw Main'));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.mic_none_rounded));

    var recording = false;
    for (var i = 0; i < 20 && !recording; i++) {
      await tester.pump(const Duration(milliseconds: 100));
      recording = find.text('Recording').evaluate().isNotEmpty;
    }
    expect(recording, isTrue);

    // The chat composer may have owned the software keyboard. Give its
    // dismissal animation time to restore the full-height capture layout.
    for (var i = 0; i < 8; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    await tester.tap(find.byIcon(Icons.stop_rounded));
    var preview = false;
    for (var i = 0; i < 80 && !preview; i++) {
      await tester.pump(const Duration(milliseconds: 250));
      preview = find.text('Voice preview').evaluate().isNotEmpty;
    }
    expect(preview, isTrue);
    expect(find.text('stub voice transcript'), findsOneWidget);
    expect(find.textContaining('stub voice reply'), findsNothing);

    await tester.enterText(
      find.byKey(const ValueKey('voice-transcript')),
      'edited stub voice transcript',
    );
    FocusManager.instance.primaryFocus?.unfocus();
    for (var i = 0; i < 8; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    await tester.tap(find.text('Send'));

    var replyFound = false;
    for (var i = 0; i < 80 && !replyFound; i++) {
      await tester.pump(const Duration(milliseconds: 250));
      replyFound = find.textContaining('stub voice reply').evaluate().isNotEmpty;
    }
    expect(replyFound, isTrue);
    expect(find.text('edited stub voice transcript'), findsWidgets);
  });
}

class _IntegrationVoiceCapture implements VoiceCapture {
  final _amplitudes = StreamController<double>.broadcast();
  late final File _file;

  @override
  Stream<double> get amplitudes => _amplitudes.stream;

  @override
  Future<void> start() async {
    _file = File(
      '${Directory.systemTemp.path}/jb-homebase-integration-voice.m4a',
    );
    await _file.writeAsBytes(<int>[0, 1, 2, 3, 4]);
    _amplitudes.add(0.7);
  }

  @override
  Future<String> stop() async => _file.path;

  @override
  Future<void> cancel() async {
    if (await _file.exists()) await _file.delete();
  }

  @override
  Future<void> dispose() async {
    await _amplitudes.close();
  }
}
