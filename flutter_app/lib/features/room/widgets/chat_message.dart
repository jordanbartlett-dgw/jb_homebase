import 'package:flutter/material.dart';

import '../../../shared/models/message.dart';
import '../../../theme/colors.dart';
import '../../../theme/spacing.dart';

/// Renders a single user or assistant message bubble.
class ChatMessage extends StatelessWidget {
  const ChatMessage({super.key, required this.message});

  final Message message;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == MessageRole.user;
    final textTheme = Theme.of(context).textTheme;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.82,
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: Spacing.lg,
          vertical: Spacing.md,
        ),
        decoration: BoxDecoration(
          color: isUser ? AppColors.accent : AppColors.surface,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(14),
            topRight: const Radius.circular(14),
            bottomLeft: Radius.circular(isUser ? 14 : 4),
            bottomRight: Radius.circular(isUser ? 4 : 14),
          ),
          boxShadow: isUser
              ? null
              : const [
                  BoxShadow(color: AppColors.shadow, blurRadius: 8, offset: Offset(0, 1)),
                ],
        ),
        child: Text(
          message.body,
          style: textTheme.bodyLarge?.copyWith(
            color: isUser ? AppColors.onAccent : AppColors.textPrimary,
          ),
        ),
      ),
    );
  }
}
