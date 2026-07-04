import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../shared/api/mock_data.dart';
import '../../theme/colors.dart';
import '../../theme/motion.dart';
import '../../theme/spacing.dart';
import '../drawer/app_drawer.dart';
import 'widgets/room_header.dart';

/// The Room shell — header + three-tab bar + the active tab body. The
/// nested route provides the body via `child`.
class RoomScreen extends ConsumerWidget {
  const RoomScreen({super.key, required this.roomId, required this.child});

  final String roomId;
  final Widget child;

  int _indexForLocation(String location) {
    if (location.endsWith('/context')) return 1;
    if (location.endsWith('/history')) return 2;
    return 0;
  }

  void _onTabSelected(BuildContext context, int index) {
    switch (index) {
      case 0:
        context.go(Routes.roomChat(roomId));
      case 1:
        context.go(Routes.roomContext(roomId));
      case 2:
        context.go(Routes.roomHistory(roomId));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final room = MockData.roomById(roomId) ?? MockData.activeRoom;
    final location = GoRouterState.of(context).matchedLocation;
    final currentIndex = _indexForLocation(location);

    return Scaffold(
      drawer: const AppDrawer(),
      appBar: AppBar(
        title: Text(room.name),
        leading: Builder(
          builder: (context) => IconButton(
            icon: const Icon(Icons.menu),
            onPressed: () => Scaffold.of(context).openDrawer(),
          ),
        ),
      ),
      body: Column(
        children: [
          RoomHeader(room: room),
          Container(
            color: AppColors.background,
            padding: const EdgeInsets.symmetric(horizontal: Spacing.md),
            child: _TabBar(
              currentIndex: currentIndex,
              onTap: (index) => _onTabSelected(context, index),
            ),
          ),
          const Divider(height: 1),
          Expanded(child: child),
        ],
      ),
    );
  }
}

class _TabBar extends StatelessWidget {
  const _TabBar({required this.currentIndex, required this.onTap});

  final int currentIndex;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    const labels = ['Chat', 'Context', 'History'];

    return Row(
      children: [
        for (var i = 0; i < labels.length; i++)
          Expanded(
            child: _TabButton(
              label: labels[i],
              selected: i == currentIndex,
              onTap: () => onTap(i),
            ),
          ),
      ],
    );
  }
}

class _TabButton extends StatelessWidget {
  const _TabButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return InkWell(
      onTap: onTap,
      child: AnimatedContainer(
        duration: Motion.medium,
        curve: Motion.ease,
        padding: const EdgeInsets.symmetric(vertical: Spacing.md),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(
              color: selected ? AppColors.accent : Colors.transparent,
              width: 2,
            ),
          ),
        ),
        child: Center(
          child: AnimatedDefaultTextStyle(
            duration: Motion.medium,
            curve: Motion.ease,
            style: textTheme.labelLarge!.copyWith(
              color: selected ? AppColors.accent : AppColors.textSecondary,
            ),
            child: Text(label),
          ),
        ),
      ),
    );
  }
}
