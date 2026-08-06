import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../routing/routes.dart';
import '../../../shared/models/workout_week.dart';
import '../../../shared/widgets/bouncy_button.dart';
import '../../../state/workout_week_state.dart';
import '../../../theme/app_theme.dart';
import '../week_schedule_screen.dart';

/// Dashboard summary: today's session plus a 7-chip week strip.
class ThisWeekCard extends ConsumerWidget {
  const ThisWeekCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final week = ref.watch(workoutWeekControllerProvider);

    return week.maybeWhen(
      data: (data) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('THIS WEEK', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          BouncyButton(
            onTap: () => context.push(Routes.training),
            child: Container(
              key: const ValueKey('this-week-card'),
              width: double.infinity,
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: theme.colorScheme.surface,
                borderRadius: BorderRadius.circular(AppTheme.radiusCard),
                border: Border.all(color: theme.colorScheme.outlineVariant),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(_headline(data), style: theme.textTheme.titleMedium),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      for (final day in data.days) ...[
                        Expanded(child: _DayChip(day: day)),
                        if (day != data.days.last) const SizedBox(width: 6),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
      orElse: () => const SizedBox.shrink(),
    );
  }

  String _headline(WorkoutWeek data) {
    if (data.planStatus != PlanStatus.active) {
      return 'No active plan. Ask your coach.';
    }
    final today = data.today;
    final planned = today?.planned;
    if (planned == null || planned.sessionType == 'rest') {
      return planned == null ? 'Nothing planned today' : 'Rest day today';
    }
    return 'Today: ${planned.description}';
  }
}

class _DayChip extends StatelessWidget {
  const _DayChip({required this.day});

  final WorkoutDay day;

  static const _letters = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final letter = _letters[day.date.weekday - 1];
    final verdictTint = day.status == DayStatus.logged && day.logs.isNotEmpty
        ? verdictColor(context, day.logs.first.verdict)
        : null;

    final (background, border, foreground) = switch (day.status) {
      DayStatus.logged => (
          verdictTint!.withValues(alpha: 0.16),
          verdictTint,
          verdictTint,
        ),
      DayStatus.today || DayStatus.upcoming => (
          Colors.transparent,
          theme.colorScheme.primary,
          theme.colorScheme.primary,
        ),
      _ => (
          Colors.transparent,
          theme.colorScheme.outlineVariant,
          theme.colorScheme.onSurfaceVariant,
        ),
    };

    return Container(
      key: ValueKey('week-chip-${day.date.weekday}'),
      height: 34,
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: border,
          width: day.isToday ? 1.8 : 1,
        ),
      ),
      alignment: Alignment.center,
      child: Text(
        letter,
        style: theme.textTheme.labelMedium?.copyWith(color: foreground),
      ),
    );
  }
}
