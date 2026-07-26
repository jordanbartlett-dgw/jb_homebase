import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:jb_homebase_app/features/voice/voice_capture.dart';
import 'package:jb_homebase_app/features/voice/voice_draft.dart';
import 'package:jb_homebase_app/features/voice/voice_overlay.dart';
import 'package:jb_homebase_app/features/voice/voice_preview.dart';
import 'package:jb_homebase_app/features/voice/voice_providers.dart';
import 'package:jb_homebase_app/features/voice/voice_service.dart';
import 'package:jb_homebase_app/routing/routes.dart';
import 'package:jb_homebase_app/shared/api/api_client.dart';
import 'package:jb_homebase_app/shared/widgets/bouncy_button.dart';
import 'package:jb_homebase_app/state/app_state.dart';

const draft = VoiceDraft(
  audioPath: '/tmp/widget-voice.m4a',
  transcript: 'original transcript',
  idempotencyKey: 'widget-draft',
  duration: Duration(seconds: 8),
);

class FakeVoiceCapture implements VoiceCapture {
  final amplitudesController = StreamController<double>.broadcast();
  bool started = false;
  bool stopped = false;
  bool cancelled = false;

  @override
  Stream<double> get amplitudes => amplitudesController.stream;

  @override
  Future<void> start() async => started = true;

  @override
  Future<String> stop() async {
    stopped = true;
    return draft.audioPath;
  }

  @override
  Future<void> cancel() async => cancelled = true;

  @override
  Future<void> dispose() => amplitudesController.close();
}

class FakeVoiceService implements VoiceService {
  int transcribeCount = 0;
  String? sentTranscript;

  @override
  Future<VoiceDraft> transcribe({
    required String audioPath,
    required Duration duration,
  }) async {
    transcribeCount++;
    return draft;
  }

  @override
  Future<AgentReply> send({
    required VoiceDraft draft,
    required String transcript,
  }) async {
    sentTranscript = transcript;
    return AgentReply(
      agentSlug: 'workout-coach',
      transcript: transcript,
      reply: 'Voice reply landed.',
    );
  }
}

void main() {
  testWidgets('recording stop transcribes into an unsent preview', (tester) async {
    final capture = FakeVoiceCapture();
    final service = FakeVoiceService();
    final router = GoRouter(
      initialLocation: Routes.voice,
      routes: [
        GoRoute(
          path: Routes.voice,
          builder: (context, state) => const VoiceOverlay(),
        ),
        GoRoute(
          path: Routes.voicePreview,
          builder: (context, state) => VoicePreview(
            draft: state.extra! as VoiceDraft,
            enableAudioPlayback: false,
          ),
        ),
      ],
    );
    addTearDown(router.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          voiceCaptureProvider.overrideWithValue(capture),
          voiceServiceProvider.overrideWithValue(service),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pump();

    expect(capture.started, isTrue);
    expect(find.text('Recording'), findsOneWidget);

    capture.amplitudesController.add(0.8);
    await tester.pump(const Duration(milliseconds: 100));
    final stopButton = tester.widget<BouncyButton>(
      find.ancestor(
        of: find.text('Stop'),
        matching: find.byType(BouncyButton),
      ),
    );
    stopButton.onTap!.call();
    for (var i = 0; i < 8; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(capture.stopped, isTrue);
    expect(service.transcribeCount, 1);
    expect(find.text('Voice preview'), findsOneWidget);
    expect(find.text('original transcript'), findsOneWidget);
    expect(service.sentTranscript, isNull);
  });

  testWidgets('reviewed transcript is editable and sent to the routed agent', (tester) async {
    final service = FakeVoiceService();
    late final GoRouter router;
    router = GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => const VoicePreview(
            draft: draft,
            enableAudioPlayback: false,
          ),
        ),
        GoRoute(
          path: '/agents',
          builder: (context, state) => const Scaffold(body: Text('Agent chat')),
        ),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          voiceServiceProvider.overrideWithValue(service),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey('voice-transcript')),
      'edited transcript',
    );
    await tester.tap(find.text('Send'));
    for (var i = 0; i < 8; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }

    expect(service.sentTranscript, 'edited transcript');
    expect(find.text('Agent chat'), findsOneWidget);

    final container = ProviderScope.containerOf(
      tester.element(find.text('Agent chat')),
    );
    expect(container.read(activeAgentProvider).id, 'workout-coach');
    final messages = await container.read(agentThreadProvider('workout-coach').future);
    expect(messages[messages.length - 2].body, 'edited transcript');
    expect(messages.last.body, 'Voice reply landed.');
  });
}
