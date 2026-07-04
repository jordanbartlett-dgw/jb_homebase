import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../state/app_state.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../../shared/widgets/bottom_action_bar.dart';
import '../drawer/app_drawer.dart';
import 'widgets/today_card.dart';

/// Today is the default landing surface. Three curated cards, max.
class TodayScreen extends ConsumerWidget {
  const TodayScreen({super.key});

  Future<void> _refresh(WidgetRef ref) async {
    // TODO(backend): refetch /api/today/cards.
    // For now this is a no-op so pull-to-refresh has a haptic without errors.
    await Future<void>.delayed(const Duration(milliseconds: 400));
    debugPrint('Today: pull-to-refresh stub fired');
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cards = ref.watch(todayCardsProvider);
    final activeRoom = ref.watch(activeRoomProvider);

    return Scaffold(
      drawer: const AppDrawer(),
      appBar: AppBar(
        title: const Text('Today'),
        titleTextStyle: Theme.of(context).textTheme.headlineMedium,
      ),
      body: RefreshIndicator(
        color: AppColors.accent,
        onRefresh: () => _refresh(ref),
        child: ListView.separated(
          padding: const EdgeInsets.fromLTRB(
            Spacing.lg,
            Spacing.md,
            Spacing.lg,
            Spacing.xxl,
          ),
          itemCount: cards.length,
          separatorBuilder: (_, _) => const SizedBox(height: Spacing.md),
          itemBuilder: (context, index) {
            final card = cards[index];
            return TodayCardView(
              card: card,
              onTap: () {
                // TODO(backend): expand card detail; deep-link if relevant.
                debugPrint('Today: card tapped ${card.id}');
              },
            );
          },
        ),
      ),
      bottomNavigationBar: BottomActionBar(
        center: _ChatCta(
          label: 'Chat with ${activeRoom.name}',
          onPressed: () => context.go(Routes.roomChat(activeRoom.id)),
        ),
        trailing: IconButton(
          onPressed: () {
            context.go(Routes.roomChat(activeRoom.id));
          },
          icon: const Icon(Icons.edit_outlined, color: AppColors.textPrimary),
          tooltip: 'New conversation',
        ),
      ),
    );
  }
}

class _ChatCta extends StatelessWidget {
  const _ChatCta({required this.label, required this.onPressed});

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return FilledButton(
      onPressed: onPressed,
      child: Text(label),
    );
  }
}
