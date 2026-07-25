import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../routing/routes.dart';
import '../../shared/models/today.dart';
import '../../shared/widgets/calendar_event_tile.dart';
import '../../state/app_state.dart';
import '../../state/today_state.dart';
import '../../theme/app_theme.dart';

class CalendarScreen extends ConsumerWidget {
  const CalendarScreen({super.key});

  void _askClaw(BuildContext context, WidgetRef ref) {
    ref.read(activeAgentProvider.notifier).select('claw-main');
    context.go(Routes.agents);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final today = ref.watch(todayControllerProvider);
    final theme = Theme.of(context);

    return SafeArea(
      child: Column(
        children: [
          Padding(
            padding: AppTheme.pagePadding.copyWith(top: 10, bottom: 10),
            child: Row(
              children: [
                IconButton(
                  tooltip: 'Back to Home',
                  onPressed: context.pop,
                  icon: const Icon(Icons.arrow_back_rounded),
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: Text(
                    'Calendar',
                    style: theme.textTheme.titleLarge,
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: today.when(
              loading: () => const Center(
                child: CircularProgressIndicator(),
              ),
              error: (error, _) => Center(
                child: OutlinedButton(
                  onPressed: () => ref.invalidate(todayControllerProvider),
                  child: const Text('Try loading again'),
                ),
              ),
              data: (overview) => RefreshIndicator(
                onRefresh: () => ref.read(todayControllerProvider.notifier).refreshToday(),
                child: ListView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: AppTheme.pagePadding.copyWith(
                    top: 22,
                    bottom: 120,
                  ),
                  children: [
                    Text(
                      'NEXT 7 DAYS',
                      style: theme.textTheme.titleSmall,
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Your Fastmail agenda',
                      style: theme.textTheme.displayMedium,
                    ),
                    const SizedBox(height: 24),
                    if (!overview.calendarAvailable)
                      _CalendarUnavailable(
                        message: overview.calendarMessage,
                      )
                    else if (overview.events.isEmpty)
                      const _EmptyCalendar()
                    else
                      ..._groupedEvents(context, overview.events),
                    const SizedBox(height: 24),
                    OutlinedButton.icon(
                      onPressed: () => _askClaw(context, ref),
                      icon: const Icon(Icons.auto_awesome_outlined),
                      label: const Text('Ask Claw about your calendar'),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _groupedEvents(
    BuildContext context,
    List<CalendarEvent> events,
  ) {
    final widgets = <Widget>[];
    DateTime? currentDay;
    for (final event in events) {
      final local = event.startsAt.toLocal();
      final day = DateTime(local.year, local.month, local.day);
      if (day != currentDay) {
        if (widgets.isNotEmpty) widgets.add(const SizedBox(height: 22));
        widgets.add(
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Text(
              DateFormat('EEEE, MMMM d').format(day).toUpperCase(),
              style: Theme.of(context).textTheme.titleSmall,
            ),
          ),
        );
        currentDay = day;
      }
      widgets.add(
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: CalendarEventTile(event: event, showDate: false),
        ),
      );
    }
    return widgets;
  }
}

class _CalendarUnavailable extends StatelessWidget {
  const _CalendarUnavailable({required this.message});

  final String? message;

  @override
  Widget build(BuildContext context) {
    return _CalendarStateCard(
      icon: Icons.cloud_off_outlined,
      text: message ?? 'Calendar is temporarily unavailable.',
    );
  }
}

class _EmptyCalendar extends StatelessWidget {
  const _EmptyCalendar();

  @override
  Widget build(BuildContext context) {
    return const _CalendarStateCard(
      icon: Icons.event_available_outlined,
      text: 'Your calendar is clear for the next seven days.',
    );
  }
}

class _CalendarStateCard extends StatelessWidget {
  const _CalendarStateCard({
    required this.icon,
    required this.text,
  });

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(AppTheme.radiusCard),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Column(
        children: [
          Icon(icon, color: theme.colorScheme.primary, size: 34),
          const SizedBox(height: 12),
          Text(
            text,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyLarge,
          ),
        ],
      ),
    );
  }
}
