import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../theme/app_theme.dart';
import '../models/today.dart';

class CalendarEventTile extends StatelessWidget {
  const CalendarEventTile({
    super.key,
    required this.event,
    this.showDate = true,
  });

  final CalendarEvent event;
  final bool showDate;

  String get _timeLabel {
    if (event.allDay) return 'All day';
    final start = DateFormat.jm().format(event.startsAt.toLocal());
    final end = DateFormat.jm().format(event.endsAt.toLocal());
    return '$start – $end';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final localStart = event.startsAt.toLocal();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(AppTheme.radiusCard),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 4,
            height: 44,
            decoration: BoxDecoration(
              color: theme.colorScheme.primary,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(event.title, style: theme.textTheme.titleMedium),
                const SizedBox(height: 4),
                Text(
                  [
                    if (showDate) DateFormat('EEE, MMM d').format(localStart),
                    _timeLabel,
                  ].join(' · '),
                  style: theme.textTheme.bodySmall,
                ),
                if (event.location case final location?) ...[
                  const SizedBox(height: 4),
                  Row(
                    children: [
                      Icon(
                        Icons.location_on_outlined,
                        size: 14,
                        color: theme.colorScheme.outline,
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          location,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodySmall,
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
