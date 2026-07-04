import 'package:flutter/material.dart';

import '../../../shared/widgets/app_card.dart';
import '../../../theme/colors.dart';
import '../../../theme/spacing.dart';
import '../models/today_card_model.dart';

/// Renders one Today card with the right accent treatment per kind.
class TodayCardView extends StatelessWidget {
  const TodayCardView({super.key, required this.card, this.onTap});

  final TodayCard card;
  final VoidCallback? onTap;

  Color _accentFor(TodayCardKind kind) {
    switch (kind) {
      case TodayCardKind.morningBriefing:
        return AppColors.accent;
      case TodayCardKind.weeklyReview:
        return AppColors.success;
      case TodayCardKind.lowRatingAlert:
        return AppColors.warning;
    }
  }

  IconData _iconFor(TodayCardKind kind) {
    switch (kind) {
      case TodayCardKind.morningBriefing:
        return Icons.wb_sunny_outlined;
      case TodayCardKind.weeklyReview:
        return Icons.calendar_view_week_outlined;
      case TodayCardKind.lowRatingAlert:
        return Icons.warning_amber_outlined;
    }
  }

  @override
  Widget build(BuildContext context) {
    final accent = _accentFor(card.kind);
    final textTheme = Theme.of(context).textTheme;

    return AppCard(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(_iconFor(card.kind), color: accent, size: 18),
              ),
              const SizedBox(width: Spacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(card.title, style: textTheme.titleMedium),
                    if (card.subtitle != null)
                      Text(
                        card.subtitle!,
                        style: textTheme.bodySmall,
                      ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: Spacing.md),
          Text(card.body, style: textTheme.bodyMedium),
        ],
      ),
    );
  }
}
