import 'package:flutter/foundation.dart';

import 'message.dart';

@immutable
class ConversationSummary {
  const ConversationSummary({
    required this.id,
    required this.agentSlug,
    required this.status,
    required this.title,
    required this.messageCount,
    required this.createdAt,
    required this.lastMessageAt,
  });

  final String id;
  final String agentSlug;
  final String status;
  final String title;
  final int messageCount;
  final DateTime createdAt;
  final DateTime lastMessageAt;

  bool get isActive => status == 'active';
}

@immutable
class ConversationDetail {
  const ConversationDetail({
    required this.conversation,
    required this.messages,
  });

  final ConversationSummary conversation;
  final List<Message> messages;
}

@immutable
class ConversationPage {
  const ConversationPage({
    required this.conversations,
    required this.nextBefore,
  });

  final List<ConversationSummary> conversations;
  final String? nextBefore;
}
