class ConversationMessagePayload {
  const ConversationMessagePayload({
    required this.id,
    required this.role,
    required this.content,
    required this.createdAt,
  });

  factory ConversationMessagePayload.fromJson(Map<String, dynamic> json) {
    return ConversationMessagePayload(
      id: json['id'] as String,
      role: json['role'] as String,
      content: json['content'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  final String id;
  final String role;
  final String content;
  final DateTime createdAt;
}

class ConversationSummaryPayload {
  const ConversationSummaryPayload({
    required this.id,
    required this.agentSlug,
    required this.status,
    required this.title,
    required this.messageCount,
    required this.createdAt,
    required this.lastMessageAt,
  });

  factory ConversationSummaryPayload.fromJson(Map<String, dynamic> json) {
    return ConversationSummaryPayload(
      id: json['id'] as String,
      agentSlug: json['agent_slug'] as String,
      status: json['status'] as String,
      title: json['title'] as String,
      messageCount: json['message_count'] as int,
      createdAt: DateTime.parse(json['created_at'] as String),
      lastMessageAt: DateTime.parse(json['last_message_at'] as String),
    );
  }

  final String id;
  final String agentSlug;
  final String status;
  final String title;
  final int messageCount;
  final DateTime createdAt;
  final DateTime lastMessageAt;
}

class ConversationDetailPayload {
  const ConversationDetailPayload({
    required this.conversation,
    required this.messages,
  });

  factory ConversationDetailPayload.fromJson(Map<String, dynamic> json) {
    return ConversationDetailPayload(
      conversation: ConversationSummaryPayload.fromJson(
        json['conversation'] as Map<String, dynamic>,
      ),
      messages: [
        for (final item in json['messages'] as List<dynamic>)
          ConversationMessagePayload.fromJson(item as Map<String, dynamic>),
      ],
    );
  }

  final ConversationSummaryPayload conversation;
  final List<ConversationMessagePayload> messages;
}

class ConversationPagePayload {
  const ConversationPagePayload({
    required this.conversations,
    required this.nextBefore,
  });

  factory ConversationPagePayload.fromJson(Map<String, dynamic> json) {
    return ConversationPagePayload(
      conversations: [
        for (final item in json['conversations'] as List<dynamic>)
          ConversationSummaryPayload.fromJson(item as Map<String, dynamic>),
      ],
      nextBefore: json['next_before'] as String?,
    );
  }

  final List<ConversationSummaryPayload> conversations;
  final String? nextBefore;
}
