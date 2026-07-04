import 'package:flutter/material.dart';

import '../../../shared/models/message.dart';
import '../../../theme/colors.dart';
import '../../../theme/spacing.dart';

/// Renders a single message.
///
/// User messages sit right in a moss bubble. Assistant messages render as
/// plain full-width text — no bubble — so long answers read like a page,
/// the way modern AI clients treat assistant output.
class ChatMessage extends StatelessWidget {
  const ChatMessage({super.key, required this.message});

  final Message message;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    if (message.role == MessageRole.assistant) {
      return Align(
        alignment: Alignment.centerLeft,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: Spacing.xs),
          child: Text(
            message.body,
            style: textTheme.bodyLarge?.copyWith(height: 1.55),
          ),
        ),
      );
    }

    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.78,
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: Spacing.lg,
          vertical: Spacing.md,
        ),
        decoration: const BoxDecoration(
          color: AppColors.accent,
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(18),
            topRight: Radius.circular(18),
            bottomLeft: Radius.circular(18),
            bottomRight: Radius.circular(6),
          ),
        ),
        child: Text(
          message.body,
          style: textTheme.bodyLarge?.copyWith(color: AppColors.onAccent),
        ),
      ),
    );
  }
}
