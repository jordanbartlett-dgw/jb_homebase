import '../models/message.dart';

/// All mock data for the design build. Replace with real API calls in PR2.
///
/// Times are computed relative to a reference moment so the UI looks
/// reasonable on any launch day. Real timestamps come from the server.
class MockData {
  const MockData._();

  static DateTime get _now => DateTime(2026, 7, 4, 8, 15);

  // ---------------------------------------------------------------------------
  // Daily digest (dashboard hero card). Server-generated in PR2.
  // ---------------------------------------------------------------------------

  static const String digestHeadline = '3 things need your attention';
  static const String digestBody =
      'Zone 2 session scheduled, two agent tasks completed overnight, '
      'and your weekly review is ready.';

  // ---------------------------------------------------------------------------
  // Chat threads, keyed by agent id.
  // ---------------------------------------------------------------------------

  static List<Message> threadFor(String agentId) => switch (agentId) {
        'workout-coach' => [
            Message(
              id: 'workout-1',
              role: MessageRole.assistant,
              body: 'Hill repeats today: 6 x 90s at the neighborhood hill. '
                  'Ready when you are.',
              timestamp: _now.subtract(const Duration(minutes: 40)),
            ),
          ],
        _ => [
            Message(
              id: 'main-1',
              role: MessageRole.user,
              body: 'What is on my plate before the FG board call?',
              timestamp: _now.subtract(const Duration(minutes: 20)),
            ),
            Message(
              id: 'main-2',
              role: MessageRole.assistant,
              body: 'Two quotes in SAGE that need follow-up by noon, and the '
                  'FG board agenda review. I can pull both up.',
              timestamp:
                  _now.subtract(const Duration(minutes: 19, seconds: 30)),
            ),
            Message(
              id: 'main-3',
              role: MessageRole.user,
              body: 'Pull the SAGE quotes.',
              timestamp: _now.subtract(const Duration(minutes: 18)),
            ),
            Message(
              id: 'main-4',
              role: MessageRole.toolCall,
              body: '',
              timestamp:
                  _now.subtract(const Duration(minutes: 17, seconds: 45)),
              toolName: 'sage_connect.search_quotes',
              toolStatus: ToolCallStatus.success,
              toolDetail: 'Searched SAGE — 2 open quotes found',
            ),
            Message(
              id: 'main-5',
              role: MessageRole.assistant,
              body: 'Found two open quotes. Quote 4421 is waiting on artwork '
                  'approval from the client. Quote 4438 needs a vendor '
                  'response on lead time. Want the contact details for both?',
              timestamp: _now.subtract(const Duration(minutes: 17)),
            ),
          ],
      };
}
