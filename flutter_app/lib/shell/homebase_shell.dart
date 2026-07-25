import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../shared/widgets/bouncy_button.dart';
import '../theme/app_theme.dart';

/// HomebaseShell — root layout around the three tab branches.
///
/// Mobile: content + floating pill nav. Wide screens (>= 840dp): the same
/// tabs render as a NavigationRail on the left — the NotebookLM-style
/// desktop posture. go_router's StatefulShellRoute keeps each branch's
/// state (chat thread, scroll positions) alive across switches.
class HomebaseShell extends StatelessWidget {
  const HomebaseShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  static const _tabs = [
    (icon: Icons.grid_view_rounded, label: 'Home'),
    (icon: Icons.chat_bubble_outline_rounded, label: 'Agents'),
    (icon: Icons.insights_rounded, label: 'Insights'),
  ];

  void _select(int index) {
    navigationShell.goBranch(
      index,
      // Re-tapping the active tab resets that branch to its root.
      initialLocation: index == navigationShell.currentIndex,
    );
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.of(context).size.width >= 840;

    if (wide) {
      return Scaffold(
        body: Row(
          children: [
            NavigationRail(
              backgroundColor: Theme.of(context).colorScheme.surface,
              indicatorColor: Theme.of(context).colorScheme.inverseSurface,
              selectedIconTheme: IconThemeData(
                color: Theme.of(context).colorScheme.primary,
              ),
              selectedLabelTextStyle: TextStyle(
                color: Theme.of(context).colorScheme.primary,
                fontWeight: FontWeight.w600,
              ),
              selectedIndex: navigationShell.currentIndex,
              onDestinationSelected: _select,
              labelType: NavigationRailLabelType.all,
              destinations: [
                for (final t in _tabs)
                  NavigationRailDestination(
                    icon: Icon(t.icon),
                    label: Text(t.label),
                  ),
              ],
            ),
            Expanded(child: navigationShell),
          ],
        ),
      );
    }

    return Scaffold(
      extendBody: true, // content scrolls beneath the floating nav
      body: navigationShell,
      bottomNavigationBar: _FloatingNav(
        index: navigationShell.currentIndex,
        tabs: _tabs,
        onSelect: _select,
      ),
    );
  }
}

/// Floating pill navigation. The active tab expands to show its label;
/// inactive tabs collapse to icons — the expansion is the micro-interaction.
class _FloatingNav extends StatelessWidget {
  const _FloatingNav({
    required this.index,
    required this.tabs,
    required this.onSelect,
  });

  final int index;
  final List<({IconData icon, String label})> tabs;
  final void Function(int) onSelect;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      child: Container(
        margin: const EdgeInsets.fromLTRB(40, 0, 40, 12),
        padding: const EdgeInsets.all(6),
        decoration: BoxDecoration(
          color: theme.colorScheme.surface,
          borderRadius: BorderRadius.circular(40),
          boxShadow: AppTheme.softShadow(context),
          border: Border.all(color: theme.colorScheme.outlineVariant),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: List.generate(tabs.length, (i) {
            final selected = i == index;
            return BouncyButton(
              onTap: () => onSelect(i),
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 300),
                curve: Curves.easeOutCubic,
                padding: EdgeInsets.symmetric(
                  horizontal: selected ? 18 : 14,
                  vertical: 12,
                ),
                decoration: BoxDecoration(
                  color: selected ? theme.colorScheme.inverseSurface : Colors.transparent,
                  borderRadius: BorderRadius.circular(30),
                  border: selected
                      ? Border.all(
                          color: theme.colorScheme.primary.withValues(alpha: 0.6),
                        )
                      : null,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      tabs[i].icon,
                      size: 22,
                      color: selected
                          ? theme.colorScheme.onInverseSurface
                          : theme.colorScheme.onSurface.withValues(alpha: 0.65),
                    ),
                    // Label slides open only for the active tab.
                    AnimatedSize(
                      duration: const Duration(milliseconds: 300),
                      curve: Curves.easeOutCubic,
                      child: selected
                          ? Padding(
                              padding: const EdgeInsets.only(left: 8),
                              child: Text(
                                tabs[i].label,
                                style: theme.textTheme.labelLarge?.copyWith(
                                  color: theme.colorScheme.onInverseSurface,
                                ),
                              ),
                            )
                          : const SizedBox.shrink(),
                    ),
                    if (selected) ...[
                      const SizedBox(width: 8),
                      Container(
                        width: 6,
                        height: 6,
                        decoration: BoxDecoration(
                          color: theme.colorScheme.primary,
                          shape: BoxShape.circle,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}
