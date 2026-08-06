import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../shared/models/workout_week.dart';
import '../../shared/widgets/fade_slide_in.dart';
import '../../state/workout_week_state.dart';
import '../../theme/app_theme.dart';

/// Verdict tint shared by the week screen and the dashboard card.
Color verdictColor(BuildContext context, OverloadVerdict? verdict) {
  final scheme = Theme.of(context).colorScheme;
  final isDark = Theme.of(context).brightness == Brightness.dark;
  return switch (verdict) {
    OverloadVerdict.positive => isDark ? const Color(0xFF7FBF8E) : const Color(0xFF3E7A4E),
    OverloadVerdict.negative => scheme.error,
    OverloadVerdict.none || OverloadVerdict.noBaseline || null => scheme.onSurfaceVariant,
  };
}

String verdictLabel(OverloadVerdict verdict) => switch (verdict) {
      OverloadVerdict.positive => 'Overload +',
      OverloadVerdict.negative => 'Overload -',
      OverloadVerdict.none => 'Held steady',
      OverloadVerdict.noBaseline => 'No baseline',
    };

class WeekScheduleScreen extends ConsumerWidget {
  const WeekScheduleScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final week = ref.watch(workoutWeekControllerProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('This Week')),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => ref.read(workoutWeekControllerProvider.notifier).refreshWeek(),
          child: week.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (error, _) => ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: AppTheme.pagePadding,
              children: [
                const SizedBox(height: 80),
                Text(
                  'Couldn’t load this week’s training.',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.titleMedium,
                ),
                const SizedBox(height: 12),
                Center(
                  child: OutlinedButton(
                    onPressed: () => ref.invalidate(workoutWeekControllerProvider),
                    child: const Text('Try again'),
                  ),
                ),
              ],
            ),
            data: (data) => ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: AppTheme.pagePadding.copyWith(top: 16, bottom: 40),
              children: [
                if (data.planStatus != PlanStatus.active)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: _PlanNotice(status: data.planStatus),
                  ),
                for (final (index, day) in data.days.indexed)
                  FadeSlideIn(
                    delay: Duration(milliseconds: 40 * index),
                    child: Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: _DayTile(day: day),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _PlanNotice extends StatelessWidget {
  const _PlanNotice({required this.status});

  final PlanStatus status;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final text = status == PlanStatus.ended
        ? 'Your plan has ended. Ask your coach for the next block.'
        : 'No active plan. Ask your coach to set one up.';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(AppTheme.radiusCard),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Text(text, style: theme.textTheme.bodyMedium),
    );
  }
}

class _DayTile extends StatelessWidget {
  const _DayTile({required this.day});

  final WorkoutDay day;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final highlight = day.isToday;

    return Container(
      key: ValueKey('day-tile-${day.date.toIso8601String().substring(0, 10)}'),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(AppTheme.radiusCard),
        border: Border.all(
          color: highlight ? theme.colorScheme.primary : theme.colorScheme.outlineVariant,
          width: highlight ? 1.6 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                DateFormat('EEEE, MMM d').format(day.date).toUpperCase(),
                style: theme.textTheme.titleSmall,
              ),
              const Spacer(),
              _StatusChip(day: day),
            ],
          ),
          const SizedBox(height: 8),
          if (day.logs.isNotEmpty)
            for (final log in day.logs) _LogRow(log: log)
          else
            Text(
              switch (day.status) {
                DayStatus.missed => 'Missed: ${day.planned?.description ?? 'planned session'}',
                DayStatus.rest => 'Rest day',
                DayStatus.empty => 'Nothing planned',
                _ => day.planned?.description ?? 'Nothing planned',
              },
              style: theme.textTheme.bodyMedium,
            ),
        ],
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.day});

  final WorkoutDay day;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (label, color) = switch (day.status) {
      DayStatus.logged => ('LOGGED', verdictColor(context, day.logs.first.verdict)),
      DayStatus.missed => ('MISSED', theme.colorScheme.onSurfaceVariant),
      DayStatus.rest => ('REST', theme.colorScheme.onSurfaceVariant),
      DayStatus.upcoming => ('UPCOMING', theme.colorScheme.primary),
      DayStatus.today => ('TODAY', theme.colorScheme.primary),
      DayStatus.empty => ('—', theme.colorScheme.onSurfaceVariant),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        label,
        style: theme.textTheme.labelSmall?.copyWith(color: color),
      ),
    );
  }
}

class _LogRow extends StatelessWidget {
  const _LogRow({required this.log});

  final LoggedWorkout log;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final detail = log.details.entries
        .where((e) => e.value is num || e.value is String)
        .map((e) => '${e.key.replaceAll('_', ' ')}: ${e.value}')
        .join(' · ');

    return InkWell(
      onTap: () => _showDetail(context),
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(log.activity.toUpperCase(), style: theme.textTheme.labelLarge),
            if (detail.isNotEmpty)
              Text(detail, style: theme.textTheme.bodySmall),
            if (log.verdict case final verdict?) ...[
              const SizedBox(height: 4),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    margin: const EdgeInsets.only(top: 5),
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: verdictColor(context, verdict),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      log.reason == null
                          ? verdictLabel(verdict)
                          : '${verdictLabel(verdict)} · ${log.reason}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: verdictColor(context, verdict),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  void _showDetail(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) {
        final theme = Theme.of(sheetContext);
        return Padding(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 40),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(log.activity.toUpperCase(), style: theme.textTheme.headlineSmall),
              const SizedBox(height: 12),
              for (final entry in log.details.entries)
                Text(
                  '${entry.key.replaceAll('_', ' ')}: ${entry.value}',
                  style: theme.textTheme.bodyMedium,
                ),
              if (log.reason case final reason?) ...[
                const SizedBox(height: 12),
                Text(
                  reason,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: verdictColor(sheetContext, log.verdict),
                  ),
                ),
              ],
              if (log.notes case final notes?) ...[
                const SizedBox(height: 12),
                Text(notes, style: theme.textTheme.bodyMedium),
              ],
            ],
          ),
        );
      },
    );
  }
}
