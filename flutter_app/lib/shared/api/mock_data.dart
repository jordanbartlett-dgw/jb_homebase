import '../models/message.dart';
import '../models/conversation.dart';

/// All mock data for the design build. Replace with real API calls in PR2.
///
/// Times are computed relative to a reference moment so the UI looks
/// reasonable on any launch day. Real timestamps come from the server.
class MockData {
  const MockData._();

  static DateTime get _now => DateTime(2026, 7, 4, 8, 15);

  // ---------------------------------------------------------------------------
  // Chat threads, keyed by agent id.
  // ---------------------------------------------------------------------------

  static List<Message> threadFor(String agentId) => switch (agentId) {
    'workout-coach' => [
      Message(
        id: 'workout-1',
        role: MessageRole.assistant,
        body:
            'Hill repeats today: 6 x 90s at the neighborhood hill. '
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
        body:
            'Two quotes in SAGE that need follow-up by noon, and the '
            'FG board agenda review. I can pull both up.',
        timestamp: _now.subtract(const Duration(minutes: 19, seconds: 30)),
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
        timestamp: _now.subtract(const Duration(minutes: 17, seconds: 45)),
        toolName: 'sage_connect.search_quotes',
        toolStatus: ToolCallStatus.success,
        toolDetail: 'Searched SAGE — 2 open quotes found',
      ),
      Message(
        id: 'main-5',
        role: MessageRole.assistant,
        body:
            'Found two open quotes. Quote 4421 is waiting on artwork '
            'approval from the client. Quote 4438 needs a vendor '
            'response on lead time. Want the contact details for both?',
        timestamp: _now.subtract(const Duration(minutes: 17)),
      ),
    ],
  };

  static List<ConversationSummary> get conversationHistory => [
    ConversationSummary(
      id: 'history-main-today',
      agentSlug: 'claw-main',
      status: 'active',
      title: 'What is on my plate before the FG board call?',
      messageCount: 5,
      createdAt: _now.subtract(const Duration(minutes: 20)),
      lastMessageAt: _now.subtract(const Duration(minutes: 17)),
    ),
    ConversationSummary(
      id: 'history-workout-yesterday',
      agentSlug: 'workout-coach',
      status: 'archived',
      title: 'Adjust this week after the hill session',
      messageCount: 2,
      createdAt: _now.subtract(const Duration(days: 1, hours: 2)),
      lastMessageAt: _now.subtract(const Duration(days: 1, hours: 1)),
    ),
    ConversationSummary(
      id: 'history-main-older',
      agentSlug: 'claw-main',
      status: 'archived',
      title: 'Summarize the open SAGE quotes',
      messageCount: 2,
      createdAt: _now.subtract(const Duration(days: 10)),
      lastMessageAt: _now.subtract(const Duration(days: 10)),
    ),
  ];

  static ConversationDetail conversationDetail(String conversationId) {
    final summary = conversationHistory.firstWhere(
      (conversation) => conversation.id == conversationId,
      orElse: () => conversationHistory.first,
    );
    return ConversationDetail(
      conversation: summary,
      messages: summary.id == 'history-main-today'
          ? threadFor('claw-main').where((message) {
              return message.role != MessageRole.toolCall;
            }).toList()
          : [
              Message(
                id: '${summary.id}-user',
                role: MessageRole.user,
                body: summary.title,
                timestamp: summary.createdAt,
              ),
              Message(
                id: '${summary.id}-assistant',
                role: MessageRole.assistant,
                body: summary.agentSlug == 'workout-coach'
                    ? 'I adjusted the week and kept your recovery day intact.'
                    : 'I found the relevant details and summarized the next actions.',
                timestamp: summary.lastMessageAt,
              ),
            ],
    );
  }
}
