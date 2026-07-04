import 'package:flutter/material.dart';

import '../../../shared/models/room.dart';
import '../../../theme/colors.dart';
import '../../../theme/spacing.dart';

/// Persistent header showing agent name, icon, and a one-line context
/// summary ("12 skills, memory on, Obsidian indexed").
class RoomHeader extends StatelessWidget {
  const RoomHeader({super.key, required this.room});

  final Room room;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Container(
      padding: const EdgeInsets.fromLTRB(
        Spacing.lg,
        Spacing.sm,
        Spacing.lg,
        Spacing.md,
      ),
      decoration: const BoxDecoration(
        color: AppColors.background,
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 18,
            backgroundColor: AppColors.accent,
            foregroundColor: AppColors.onAccent,
            child: Text(
              room.icon,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          const SizedBox(width: Spacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(room.name, style: textTheme.titleMedium),
                const SizedBox(height: 2),
                Text(room.subline, style: textTheme.bodySmall),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
