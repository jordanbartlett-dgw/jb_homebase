enum MessageStreamEventType { status, delta, complete, error }

/// One newline-delimited event from POST /app/messages/stream.
class MessageStreamEvent {
  const MessageStreamEvent({
    required this.type,
    this.message,
    this.text,
    this.agentSlug,
    this.reply,
    this.conversationId,
  });

  factory MessageStreamEvent.fromJson(Map<String, dynamic> json) {
    final type = switch (json['type']) {
      'status' => MessageStreamEventType.status,
      'delta' => MessageStreamEventType.delta,
      'complete' => MessageStreamEventType.complete,
      'error' => MessageStreamEventType.error,
      final value => throw FormatException('Unknown message stream event: $value'),
    };
    return MessageStreamEvent(
      type: type,
      message: json['message'] as String?,
      text: json['text'] as String?,
      agentSlug: json['agent_slug'] as String?,
      reply: json['reply'] as String?,
      conversationId: json['conversation_id'] as String?,
    );
  }

  final MessageStreamEventType type;
  final String? message;
  final String? text;
  final String? agentSlug;
  final String? reply;
  final String? conversationId;
}
