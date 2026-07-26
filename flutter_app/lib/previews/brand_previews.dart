import 'package:flutter/material.dart';
import 'package:flutter/widget_previews.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/chat/chat_screen.dart';
import '../features/chat/widgets/agent_welcome.dart';
import '../features/home/dashboard_screen.dart';
import '../features/history/history_screen.dart';
import '../features/voice/voice_capture.dart';
import '../features/voice/voice_draft.dart';
import '../features/voice/voice_overlay.dart';
import '../features/voice/voice_preview.dart';
import '../features/voice/voice_providers.dart';
import '../shared/models/agent.dart';
import '../theme/app_theme.dart';

/// Shared theme configuration for design review in the Flutter Widget
/// Previewer. The preview brightness control switches between both recipes.
PreviewThemeData homebasePreviewTheme() => PreviewThemeData(
  materialLight: AppTheme.light,
  materialDark: AppTheme.dark,
);

/// Supplies the Material and Riverpod context used by the app screens.
Widget homebasePreviewWrapper(Widget child) => ProviderScope(
  child: Scaffold(body: child),
);

Widget voiceCapturePreviewWrapper(Widget child) => ProviderScope(
  overrides: [
    voiceCaptureProvider.overrideWithValue(const _PreviewVoiceCapture()),
  ],
  child: child,
);

@Preview(
  name: 'Dashboard · Light',
  group: 'Monochrome + Cobalt',
  size: Size(390, 844),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
@Preview(
  name: 'Dashboard · Dark',
  group: 'Monochrome + Cobalt',
  size: Size(390, 844),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
Widget dashboardBrandPreview() => const DashboardScreen();

@Preview(
  name: 'Agents · Light',
  group: 'Monochrome + Cobalt',
  size: Size(390, 844),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
@Preview(
  name: 'Agents · Dark',
  group: 'Monochrome + Cobalt',
  size: Size(390, 844),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
Widget agentsBrandPreview() => const ChatScreen();

@Preview(
  name: 'History · Light',
  group: 'Monochrome + Cobalt',
  size: Size(390, 844),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
@Preview(
  name: 'History · Dark',
  group: 'Monochrome + Cobalt',
  size: Size(390, 844),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
Widget historyBrandPreview() => const HistoryScreen();

void selectPreviewPrompt(String _) {}

@Preview(
  name: 'Med Check Welcome · Light',
  group: 'Med Check',
  size: Size(390, 844),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
@Preview(
  name: 'Med Check Welcome · Dark',
  group: 'Med Check',
  size: Size(390, 844),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
Widget medCheckWelcomePreview() => AgentWelcome(
  agent: Agent.byId('med-check'),
  onSelectPrompt: selectPreviewPrompt,
);

@Preview(
  name: 'Voice Capture · Light',
  group: 'Voice',
  size: Size(390, 844),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: voiceCapturePreviewWrapper,
)
@Preview(
  name: 'Voice Capture · Dark',
  group: 'Voice',
  size: Size(390, 844),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: voiceCapturePreviewWrapper,
)
Widget voiceCapturePreview() => const VoiceOverlay();

@Preview(
  name: 'Voice Review · Light',
  group: 'Voice',
  size: Size(390, 844),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
@Preview(
  name: 'Voice Review · Dark',
  group: 'Voice',
  size: Size(390, 844),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
Widget voiceReviewPreview() => const VoicePreview(
  enableAudioPlayback: false,
  draft: VoiceDraft(
    audioPath: '/tmp/voice-preview.m4a',
    transcript:
        'Just got off the call with the vendor. They want forty-eight hours '
        'on the lead time, but I think we can push for thirty-six.',
    idempotencyKey: 'preview-voice',
    duration: Duration(seconds: 8),
  ),
);

class _PreviewVoiceCapture implements VoiceCapture {
  const _PreviewVoiceCapture();

  @override
  Stream<double> get amplitudes => Stream<double>.periodic(
    const Duration(milliseconds: 120),
    (tick) => <double>[0.16, 0.38, 0.72, 0.44, 0.24][tick % 5],
  );

  @override
  Future<void> start() async {}

  @override
  Future<String> stop() async => '/tmp/voice-preview.m4a';

  @override
  Future<void> cancel() async {}

  @override
  Future<void> dispose() async {}
}
