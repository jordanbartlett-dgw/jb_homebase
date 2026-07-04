import 'package:flutter/foundation.dart';

enum MessageRole { user, assistant, toolCall }

enum ToolCallStatus { inProgress, success, failure }

@immutable
class Message {
  const Message({
    required this.id,
    required this.role,
    required this.body,
    required this.timestamp,
    this.toolName,
    this.toolStatus,
    this.toolDetail,
  });

  final String id;
  final MessageRole role;
  final String body;
  final DateTime timestamp;

  // Tool-call chip fields. Populated when role == MessageRole.toolCall.
  final String? toolName;
  final ToolCallStatus? toolStatus;
  final String? toolDetail;
}
