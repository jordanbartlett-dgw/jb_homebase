import 'package:flutter/material.dart';

import '../../../shared/models/message.dart';
import '../../../theme/colors.dart';
import '../../../theme/spacing.dart';

/// Tool-call chip that appears mid-response and resolves with a checkmark
/// or error icon. No thinking traces — just the visible tool name + status.
class ToolCallChip extends StatelessWidget {
  const ToolCallChip({super.key, required this.message});

  final Message message;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final status = message.toolStatus ?? ToolCallStatus.inProgress;

    final (icon, color) = switch (status) {
      ToolCallStatus.inProgress => (Icons.sync, AppColors.textMuted),
      ToolCallStatus.success => (Icons.check_circle, AppColors.success),
      ToolCallStatus.failure => (Icons.error_outline, AppColors.error),
    };

    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: Spacing.md,
          vertical: Spacing.sm,
        ),
        decoration: BoxDecoration(
          color: AppColors.surfaceVariant,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppColors.border, width: 0.5),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (status == ToolCallStatus.inProgress)
              const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: AppColors.textMuted,
                ),
              )
            else
              Icon(icon, size: 14, color: color),
            const SizedBox(width: Spacing.sm),
            Flexible(
              child: Text(
                message.toolDetail ?? message.toolName ?? 'Running tool',
                style: textTheme.bodySmall,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
