import 'package:flutter/material.dart';
import 'package:flutter/widget_previews.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/chat/chat_screen.dart';
import '../features/chat/widgets/agent_welcome.dart';
import '../features/chat/widgets/streaming_response.dart';
import '../features/home/dashboard_screen.dart';
import '../features/home/widgets/proactive_artifact_card.dart';
import '../features/history/history_screen.dart';
import '../features/voice/voice_capture.dart';
import '../features/voice/voice_draft.dart';
import '../features/voice/voice_overlay.dart';
import '../features/voice/voice_preview.dart';
import '../features/voice/voice_providers.dart';
import '../shared/models/agent.dart';
import '../shared/models/today.dart';
import '../shared/widgets/app_markdown.dart';
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
void noopPreviewAction() {}

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
  name: 'Generated Code · Light',
  group: 'Code Mode',
  size: Size(390, 640),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
@Preview(
  name: 'Generated Code · Dark',
  group: 'Code Mode',
  size: Size(390, 640),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
Widget generatedCodePreview() => const SingleChildScrollView(
  padding: EdgeInsets.all(20),
  child: AppMarkdown(
    data: '''
I grouped the upcoming events by calendar and kept only the fields needed for the summary.

```python
import asyncio

events = await asyncio.gather(
    check_calendar(days=7),
    search_notes(query="launch checklist"),
)

summary = {
    "event_count": len(events[0]),
    "has_checklist": bool(events[1]),
}
```

The result is ready to use in the weekly review.
''',
  ),
);

@Preview(
  name: 'Streaming Response · Light',
  group: 'Chat',
  size: Size(390, 460),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
@Preview(
  name: 'Streaming Response · Dark',
  group: 'Chat',
  size: Size(390, 460),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
Widget streamingResponsePreview() => const Padding(
  padding: EdgeInsets.all(20),
  child: StreamingResponse(
    status: 'Writing response',
    partialText:
        'I checked your calendar and notes. Here’s the start of the plan:\n\n'
        '1. Review the open quote before the board call.\n'
        '2. Protect the afternoon focus block.',
  ),
);

@Preview(
  name: 'Updates · Light',
  group: 'Today',
  size: Size(390, 460),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
@Preview(
  name: 'Updates · Dark',
  group: 'Today',
  size: Size(390, 460),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
Widget proactiveUpdatesPreview() => Padding(
  padding: const EdgeInsets.all(20),
  child: Column(
    children: [
      ProactiveArtifactCard(
        artifact: ProactiveArtifact(
          taskType: 'memory_flag',
          content:
              'I updated my understanding: the vendor committed to a '
              '36-hour lead time.',
          createdAt: DateTime(2026, 7, 26, 8, 4),
        ),
        onTap: noopPreviewAction,
      ),
      const SizedBox(height: 10),
      ProactiveArtifactCard(
        artifact: ProactiveArtifact(
          taskType: 'event_trigger',
          content:
              '**Agent inbox update:** A vendor replied about quote 4438 '
              'and can meet the requested lead time.',
          createdAt: DateTime(2026, 7, 26, 7, 48),
        ),
        onTap: noopPreviewAction,
      ),
    ],
  ),
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
