import 'package:flutter/material.dart';

import '../../../shared/models/message.dart';
import '../../../theme/colors.dart';

/// Tool-call chip that appears mid-response and resolves with a checkmark
/// or error icon. No thinking traces — just the visible tool name + status.
class ToolCallChip extends StatelessWidget {
  const ToolCallChip({super.key, required this.message});

  final Message message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final status = message.toolStatus ?? ToolCallStatus.inProgress;

    final (icon, color) = switch (status) {
      ToolCallStatus.inProgress => (Icons.sync, theme.colorScheme.outline),
      ToolCallStatus.success => (Icons.check_circle, AppColors.success),
      ToolCallStatus.failure => (Icons.error_outline, theme.colorScheme.error),
    };

    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: theme.colorScheme.surfaceContainerHighest
              .withValues(alpha: 0.6),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (status == ToolCallStatus.inProgress)
              SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: theme.colorScheme.outline,
                ),
              )
            else
              Icon(icon, size: 14, color: color),
            const SizedBox(width: 8),
            Flexible(
              child: Text(
                message.toolDetail ?? message.toolName ?? 'Running tool',
                style: theme.textTheme.bodySmall,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
