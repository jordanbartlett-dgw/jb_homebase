import 'package:flutter/material.dart';

import '../../shared/widgets/fade_slide_in.dart';
import '../../shared/widgets/sparkline_card.dart';
import '../../shared/widgets/week_stripe.dart';
import '../../theme/app_theme.dart';

/// Insights tab: the analytics/calendar architecture, assembled from the
/// same placeholder widgets the dashboard previews. Grows into the full
/// analytics dashboard later (PostHog-fed).
class InsightsScreen extends StatelessWidget {
  const InsightsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      bottom: false,
      child: ListView(
        padding: AppTheme.pagePadding.copyWith(top: 24, bottom: 120),
        children: [
          FadeSlideIn(
            child: Text('Insights', style: theme.textTheme.displayMedium),
          ),
          const SizedBox(height: 24),
          const FadeSlideIn(
            delay: Duration(milliseconds: 100),
            child: WeekStripe(),
          ),
          const SizedBox(height: 16),
          const FadeSlideIn(
            delay: Duration(milliseconds: 180),
            child: SparklineCard(),
          ),
          const SizedBox(height: 16),
          const FadeSlideIn(
            delay: Duration(milliseconds: 260),
            child: SparklineCard(
              title: 'Weekly volume',
              caption: 'Hours per week, last 14 weeks',
              values: [4, 4.5, 5, 4, 6, 5.5, 6.5, 7, 6, 7.5, 8, 7, 8.5, 9],
            ),
          ),
        ],
      ),
    );
  }
}
