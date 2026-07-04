import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../shared/models/room.dart';
import '../../state/app_state.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';

/// Granola-style top-left drawer. Lists rooms, settings, and sign out.
class AppDrawer extends ConsumerWidget {
  const AppDrawer({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rooms = ref.watch(roomsProvider);
    final textTheme = Theme.of(context).textTheme;

    return Drawer(
      backgroundColor: AppColors.background,
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                Spacing.lg,
                Spacing.lg,
                Spacing.lg,
                Spacing.sm,
              ),
              child: Text('Jordan Claw', style: textTheme.titleLarge),
            ),
            const Divider(),
            Padding(
              padding: const EdgeInsets.fromLTRB(
                Spacing.lg,
                Spacing.md,
                Spacing.lg,
                Spacing.xs,
              ),
              child: Text('Rooms', style: textTheme.labelSmall),
            ),
            for (final room in rooms) _RoomTile(room: room),
            const Spacer(),
            const Divider(),
            ListTile(
              leading: const Icon(Icons.settings_outlined, color: AppColors.textPrimary),
              title: Text('Settings', style: textTheme.bodyLarge),
              onTap: () {
                Navigator.of(context).pop();
                // TODO(backend): build settings screen in PR2.
                debugPrint('Drawer: settings tapped (no-op stub)');
              },
            ),
            ListTile(
              leading: const Icon(Icons.logout, color: AppColors.textPrimary),
              title: Text('Sign out', style: textTheme.bodyLarge),
              onTap: () {
                ref.read(authControllerProvider.notifier).signOut();
                Navigator.of(context).pop();
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _RoomTile extends ConsumerWidget {
  const _RoomTile({required this.room});

  final Room room;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;
    final disabled = !room.isActive;

    return ListTile(
      leading: CircleAvatar(
        backgroundColor: disabled ? AppColors.surfaceVariant : AppColors.accent,
        foregroundColor: disabled ? AppColors.textMuted : AppColors.onAccent,
        radius: 16,
        child: Text(room.icon, style: const TextStyle(fontWeight: FontWeight.w600)),
      ),
      title: Text(
        room.name,
        style: textTheme.bodyLarge?.copyWith(
          color: disabled ? AppColors.textDisabled : AppColors.textPrimary,
        ),
      ),
      subtitle: Text(
        room.subline,
        style: textTheme.bodySmall,
      ),
      trailing: disabled
          ? Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: AppColors.surfaceVariant,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                'Coming soon',
                style: textTheme.labelSmall,
              ),
            )
          : const Icon(Icons.chevron_right, color: AppColors.textMuted),
      onTap: disabled
          ? null
          : () {
              ref.read(activeRoomProvider.notifier).setActive(room.id);
              Navigator.of(context).pop();
              context.go(Routes.roomChat(room.id));
            },
    );
  }
}
