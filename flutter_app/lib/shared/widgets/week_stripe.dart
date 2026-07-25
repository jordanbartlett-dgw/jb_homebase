import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';

/// Compact horizontal weekly calendar: today is high-contrast monochrome,
/// while cobalt activity dots carry the live state. The seed of the
/// future full calendar view.
class WeekStripe extends StatelessWidget {
  const WeekStripe({super.key, this.activeDays = const {1, 3, 5}});

  /// Weekday ints (DateTime.monday == 1) that carry an activity dot.
  final Set<int> activeDays;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final now = DateTime.now();
    final monday = now.subtract(Duration(days: now.weekday - 1));
    const labels = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(AppTheme.radiusCard),
        boxShadow: AppTheme.softShadow(context),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: List.generate(7, (i) {
          final day = monday.add(Duration(days: i));
          final isToday = day.day == now.day && day.month == now.month;
          final hasActivity = activeDays.contains(i + 1);

          return Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(labels[i], style: theme.textTheme.bodySmall),
              const SizedBox(height: 8),
              AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                width: 36,
                height: 36,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: isToday ? theme.colorScheme.inverseSurface : Colors.transparent,
                  shape: BoxShape.circle,
                ),
                child: Text(
                  '${day.day}',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: isToday ? FontWeight.w700 : FontWeight.w500,
                    color: isToday
                        ? theme.colorScheme.onInverseSurface
                        : theme.colorScheme.onSurface,
                  ),
                ),
              ),
              const SizedBox(height: 6),
              // Activity dot (invisible placeholder keeps rows aligned).
              Container(
                width: 5,
                height: 5,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: hasActivity ? theme.colorScheme.primary : Colors.transparent,
                ),
              ),
            ],
          );
        }),
      ),
    );
  }
}
