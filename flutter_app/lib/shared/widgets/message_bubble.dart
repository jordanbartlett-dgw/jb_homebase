import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';
import '../models/message.dart';
import 'app_markdown.dart';

/// Shared user/assistant bubble used by live chat and read-only history.
class MessageBubble extends StatelessWidget {
  const MessageBubble({super.key, required this.message});

  final Message message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final fromUser = message.role == MessageRole.user;
    const radius = Radius.circular(AppTheme.radiusBubble);
    const sharp = Radius.circular(4);

    return Align(
      alignment: fromUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 5),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.75,
        ),
        decoration: BoxDecoration(
          color: fromUser ? theme.colorScheme.inverseSurface : theme.colorScheme.surface,
          borderRadius: BorderRadius.only(
            topLeft: radius,
            topRight: radius,
            bottomLeft: fromUser ? radius : sharp,
            bottomRight: fromUser ? sharp : radius,
          ),
          border: fromUser ? null : Border.all(color: theme.colorScheme.outlineVariant),
        ),
        child: fromUser
            ? Text(
                message.body,
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: theme.colorScheme.onInverseSurface,
                ),
              )
            : AppMarkdown(
                data: message.body,
                color: theme.colorScheme.onSurface,
                compact: true,
              ),
      ),
    );
  }
}
