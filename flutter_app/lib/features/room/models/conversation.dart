import 'package:flutter/foundation.dart';

import '../../../shared/models/message.dart';

/// A past or active conversation inside a room.
@immutable
class Conversation {
  const Conversation({
    required this.id,
    required this.roomId,
    required this.preview,
    required this.startedAt,
    required this.messageCount,
    this.messages = const <Message>[],
  });

  final String id;
  final String roomId;
  final String preview;
  final DateTime startedAt;
  final int messageCount;
  final List<Message> messages;
}
