import 'package:flutter/material.dart';

import '../../../shared/widgets/app_card.dart';
import '../../../theme/colors.dart';
import '../../../theme/motion.dart';
import '../../../theme/spacing.dart';
import '../models/today_card_model.dart';

/// Renders one Today card with the right accent treatment per kind.
///
/// Collapsed cards preview the first two lines of the body; tapping
/// expands in place. Deep-linking into source data is PR2.
class TodayCardView extends StatefulWidget {
  const TodayCardView({super.key, required this.card});

  final TodayCard card;

  @override
  State<TodayCardView> createState() => _TodayCardViewState();
}

class _TodayCardViewState extends State<TodayCardView> {
  bool _expanded = false;

  Color get _accent {
    switch (widget.card.kind) {
      case TodayCardKind.morningBriefing:
        return AppColors.accent;
      case TodayCardKind.weeklyReview:
        return AppColors.success;
      case TodayCardKind.lowRatingAlert:
        return AppColors.warning;
    }
  }

  IconData get _icon {
    switch (widget.card.kind) {
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
    final card = widget.card;
    final textTheme = Theme.of(context).textTheme;

    return AppCard(
      onTap: () {
        // TODO(backend): deep-link into source data where relevant.
        setState(() => _expanded = !_expanded);
      },
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  color: _accent.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(_icon, color: _accent, size: 18),
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
              AnimatedRotation(
                turns: _expanded ? 0.5 : 0,
                duration: Motion.medium,
                curve: Motion.ease,
                child: const Icon(
                  Icons.keyboard_arrow_down,
                  color: AppColors.textMuted,
                  size: 20,
                ),
              ),
            ],
          ),
          const SizedBox(height: Spacing.md),
          AnimatedSize(
            duration: Motion.medium,
            curve: Motion.ease,
            alignment: Alignment.topCenter,
            child: Text(
              card.body,
              style: textTheme.bodyMedium,
              maxLines: _expanded ? null : 2,
              overflow: _expanded ? null : TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
