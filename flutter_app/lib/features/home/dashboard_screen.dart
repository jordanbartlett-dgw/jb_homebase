import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../routing/routes.dart';
import '../../shared/models/agent.dart';
import '../../shared/widgets/bouncy_button.dart';
import '../../shared/widgets/fade_slide_in.dart';
import '../../shared/widgets/sparkline_card.dart';
import '../../shared/widgets/week_stripe.dart';
import '../../state/app_state.dart';
import '../../theme/app_theme.dart';
import '../../theme/colors.dart';

/// DashboardScreen — the Homebase landing view.
/// Layout: eyebrow date → Playfair greeting → inverse digest card →
/// agent dock → insights row. Every block staggers in via FadeSlideIn.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  String get _greeting {
    final h = DateTime.now().hour;
    if (h < 12) return 'Good morning,\nJordan';
    if (h < 17) return 'Good afternoon,\nJordan';
    return 'Good evening,\nJordan';
  }

  void _openAgent(BuildContext context, WidgetRef ref, Agent agent) {
    ref.read(activeAgentProvider.notifier).select(agent.id);
    context.go(Routes.agents);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final date = DateFormat('EEEE, MMMM d').format(DateTime.now());

    return SafeArea(
      bottom: false,
      child: ListView(
        padding: AppTheme.pagePadding.copyWith(top: 24, bottom: 120),
        children: [
          // ---- Digest header -------------------------------------------
          FadeSlideIn(
            child: Text(date.toUpperCase(), style: theme.textTheme.titleSmall),
          ),
          const SizedBox(height: 8),
          FadeSlideIn(
            delay: const Duration(milliseconds: 80),
            child: Text(_greeting, style: theme.textTheme.displayLarge),
          ),
          const SizedBox(height: 24),

          // ---- Daily Digest card ---------------------------------------
          const FadeSlideIn(
            delay: Duration(milliseconds: 160),
            child: _DigestCard(),
          ),
          const SizedBox(height: 32),

          // ---- Agent dock ----------------------------------------------
          FadeSlideIn(
            delay: const Duration(milliseconds: 240),
            child: Text('YOUR AGENTS', style: theme.textTheme.titleSmall),
          ),
          const SizedBox(height: 12),
          FadeSlideIn(
            delay: const Duration(milliseconds: 300),
            child: SizedBox(
              height: 160,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                clipBehavior: Clip.none, // let shadows breathe
                itemCount: Agent.roster.length,
                separatorBuilder: (_, _) => const SizedBox(width: 14),
                itemBuilder: (context, i) => _AgentCard(
                  agent: Agent.roster[i],
                  onTap: () => _openAgent(context, ref, Agent.roster[i]),
                ),
              ),
            ),
          ),
          const SizedBox(height: 32),

          // ---- Insights ------------------------------------------------
          FadeSlideIn(
            delay: const Duration(milliseconds: 380),
            child: Text('THIS WEEK', style: theme.textTheme.titleSmall),
          ),
          const SizedBox(height: 12),
          const FadeSlideIn(
            delay: Duration(milliseconds: 440),
            child: WeekStripe(),
          ),
          const SizedBox(height: 16),
          const FadeSlideIn(
            delay: Duration(milliseconds: 500),
            child: SparklineCard(),
          ),
        ],
      ),
    );
  }
}

/// The one loud element on the page: an inverse monochrome card with a
/// cobalt live-state detail. Later this renders the real Daily Digest payload.
class _DigestCard extends StatelessWidget {
  const _DigestCard();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final heroInk = theme.colorScheme.onInverseSurface;
    final heroAccent = isDark ? AppColors.cobalt : AppColors.cobaltBright;

    return BouncyButton(
      onTap: () {}, // TODO(backend): full digest detail screen
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          color: theme.colorScheme.inverseSurface,
          borderRadius: BorderRadius.circular(AppTheme.radiusCard),
          border: Border.all(color: heroAccent.withValues(alpha: 0.7)),
          boxShadow: AppTheme.softShadow(context),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    color: heroAccent,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 10),
                Text(
                  'DAILY DIGEST',
                  style: theme.textTheme.titleSmall?.copyWith(
                    color: heroInk.withValues(alpha: 0.65),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              // TODO(backend): real digest from /api/today/cards
              '3 things need your attention',
              style: theme.textTheme.headlineSmall?.copyWith(color: heroInk),
            ),
            const SizedBox(height: 8),
            Text(
              'Zone 2 session scheduled, two agent tasks completed '
              'overnight, and your weekly review is ready.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: heroInk.withValues(alpha: 0.78),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Text(
                  'Read digest',
                  style: theme.textTheme.labelLarge?.copyWith(color: heroAccent),
                ),
                const SizedBox(width: 6),
                Icon(
                  Icons.arrow_forward_rounded,
                  size: 18,
                  color: heroAccent,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Tactile monochrome dock card with cobalt-family identity details.
class _AgentCard extends StatelessWidget {
  const _AgentCard({required this.agent, required this.onTap});

  final Agent agent;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final accent = isDark ? AppColors.cobaltBright : agent.tint;

    return BouncyButton(
      onTap: onTap,
      child: Container(
        width: 170,
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: theme.colorScheme.surface,
          borderRadius: BorderRadius.circular(AppTheme.radiusCard),
          border: Border.all(color: theme.colorScheme.outlineVariant),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: accent.withValues(alpha: isDark ? 0.16 : 0.10),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: accent.withValues(alpha: 0.28)),
              ),
              child: Icon(agent.icon, color: accent, size: 22),
            ),
            const Spacer(),
            Text(
              agent.name,
              style: theme.textTheme.titleMedium,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            const SizedBox(height: 2),
            Text(
              agent.tagline,
              style: theme.textTheme.bodySmall,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }
}
