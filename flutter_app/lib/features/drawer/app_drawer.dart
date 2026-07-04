import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../shared/models/room.dart';
import '../../shared/widgets/pressable.dart';
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
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                Spacing.lg,
                Spacing.lg,
                Spacing.lg,
                Spacing.md,
              ),
              child: Row(
                children: [
                  Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: AppColors.accent,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Center(
                      child: Text(
                        'JC',
                        style: TextStyle(
                          color: AppColors.onAccent,
                          fontWeight: FontWeight.w700,
                          fontSize: 14,
                          letterSpacing: 0.5,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: Spacing.md),
                  Text('Jordan Claw', style: textTheme.titleLarge),
                ],
              ),
            ),
            const Divider(),
            Padding(
              padding: const EdgeInsets.fromLTRB(
                Spacing.lg,
                Spacing.md,
                Spacing.lg,
                Spacing.sm,
              ),
              child: Text('ROOMS', style: textTheme.labelSmall),
            ),
            for (final room in rooms)
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: Spacing.sm,
                  vertical: 2,
                ),
                child: _RoomTile(room: room),
              ),
            const Spacer(),
            const Divider(),
            _DrawerAction(
              icon: Icons.settings_outlined,
              label: 'Settings',
              onTap: () {
                Navigator.of(context).pop();
                // TODO(backend): build settings screen in PR2.
                debugPrint('Drawer: settings tapped (no-op stub)');
              },
            ),
            _DrawerAction(
              icon: Icons.logout,
              label: 'Sign out',
              onTap: () {
                ref.read(authControllerProvider.notifier).signOut();
                Navigator.of(context).pop();
              },
            ),
            const SizedBox(height: Spacing.sm),
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
    final selected = ref.watch(activeRoomProvider).id == room.id;

    final tile = Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Spacing.md,
        vertical: Spacing.sm,
      ),
      decoration: BoxDecoration(
        color: selected ? AppColors.accentSoft : Colors.transparent,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          CircleAvatar(
            backgroundColor:
                disabled ? AppColors.surfaceVariant : AppColors.accent,
            foregroundColor:
                disabled ? AppColors.textMuted : AppColors.onAccent,
            radius: 16,
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
                Text(
                  room.name,
                  style: textTheme.bodyLarge?.copyWith(
                    color: disabled
                        ? AppColors.textDisabled
                        : AppColors.textPrimary,
                    fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                  ),
                ),
                Text(
                  room.subline,
                  style: textTheme.bodySmall,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          if (disabled)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: AppColors.surfaceVariant,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text('Coming soon', style: textTheme.labelSmall),
            )
          else
            const Icon(Icons.chevron_right,
                color: AppColors.textMuted, size: 20),
        ],
      ),
    );

    if (disabled) return tile;
    return Pressable(
      onTap: () {
        ref.read(activeRoomProvider.notifier).setActive(room.id);
        Navigator.of(context).pop();
        context.go(Routes.roomChat(room.id));
      },
      pressedScale: 0.98,
      child: tile,
    );
  }
}

class _DrawerAction extends StatelessWidget {
  const _DrawerAction({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(icon, color: AppColors.textPrimary),
      title: Text(label, style: Theme.of(context).textTheme.bodyLarge),
      onTap: onTap,
    );
  }
}
