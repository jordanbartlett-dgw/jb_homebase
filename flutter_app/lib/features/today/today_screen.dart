import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../state/app_state.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../../shared/widgets/bottom_action_bar.dart';
import '../../shared/widgets/entrance.dart';
import '../drawer/app_drawer.dart';
import 'widgets/today_card.dart';

/// Today is the default landing surface. Three curated cards, max.
class TodayScreen extends ConsumerWidget {
  const TodayScreen({super.key});

  Future<void> _refresh(WidgetRef ref) async {
    // TODO(backend): refetch /api/today/cards.
    await Future<void>.delayed(const Duration(milliseconds: 400));
    HapticFeedback.lightImpact();
    debugPrint('Today: pull-to-refresh stub fired');
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cards = ref.watch(todayCardsProvider);
    final activeRoom = ref.watch(activeRoomProvider);

    return Scaffold(
      drawer: const AppDrawer(),
      appBar: AppBar(),
      body: RefreshIndicator(
        color: AppColors.accent,
        onRefresh: () => _refresh(ref),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            Spacing.lg,
            0,
            Spacing.lg,
            Spacing.xxl,
          ),
          children: [
            const Entrance(child: _GreetingHeader()),
            const SizedBox(height: Spacing.xl),
            if (cards.isEmpty)
              const Entrance(index: 1, child: _EmptyToday())
            else
              for (var i = 0; i < cards.length; i++) ...[
                if (i > 0) const SizedBox(height: Spacing.md),
                Entrance(index: i + 1, child: TodayCardView(card: cards[i])),
              ],
          ],
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

/// Date eyebrow + time-of-day greeting. The warm, personal open that makes
/// Today feel like a briefing, not an inbox.
class _GreetingHeader extends StatelessWidget {
  const _GreetingHeader();

  static const _weekdays = [
    'Monday', 'Tuesday', 'Wednesday', 'Thursday',
    'Friday', 'Saturday', 'Sunday',
  ];
  static const _months = [
    'January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December',
  ];

  String _greetingFor(int hour) {
    if (hour < 5) return 'Still up, Jordan?';
    if (hour < 12) return 'Good morning, Jordan';
    if (hour < 17) return 'Good afternoon, Jordan';
    return 'Good evening, Jordan';
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final now = DateTime.now();
    final date =
        '${_weekdays[now.weekday - 1]}, ${_months[now.month - 1]} ${now.day}';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(date.toUpperCase(), style: textTheme.labelSmall),
        const SizedBox(height: Spacing.xs),
        Text(_greetingFor(now.hour), style: textTheme.displaySmall),
      ],
    );
  }
}

/// Shown when the feed has nothing curated — calm, not apologetic.
class _EmptyToday extends StatelessWidget {
  const _EmptyToday();

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: Spacing.xxl),
      child: Column(
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: const BoxDecoration(
              color: AppColors.accentSoft,
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.wb_sunny_outlined,
              color: AppColors.accent,
              size: 26,
            ),
          ),
          const SizedBox(height: Spacing.lg),
          Text('All clear', style: textTheme.titleMedium),
          const SizedBox(height: Spacing.xs),
          Text(
            'Nothing needs your attention right now.',
            style: textTheme.bodyMedium,
            textAlign: TextAlign.center,
          ),
        ],
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
