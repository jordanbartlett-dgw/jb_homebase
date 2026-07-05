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
/// Layout: eyebrow date → Playfair greeting → digest gradient card →
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

/// The one loud element on the page: sage gradient, soft lift, digest copy.
/// Later this renders the real Daily Digest payload from the gateway.
class _DigestCard extends StatelessWidget {
  const _DigestCard();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final gradient = isDark
        ? AppColors.digestGradientDark
        : AppColors.digestGradientLight;

    return BouncyButton(
      onTap: () {}, // TODO(backend): full digest detail screen
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: gradient,
          ),
          borderRadius: BorderRadius.circular(AppTheme.radiusCard),
          boxShadow: [
            BoxShadow(
              color: gradient.first.withValues(alpha: 0.35),
              blurRadius: 28,
              offset: const Offset(0, 14),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'DAILY DIGEST',
              style: theme.textTheme.titleSmall
                  ?.copyWith(color: AppColors.cream.withValues(alpha: 0.7)),
            ),
            const SizedBox(height: 10),
            Text(
              // TODO(backend): real digest from /api/today/cards
              '3 things need your attention',
              style: theme.textTheme.headlineSmall
                  ?.copyWith(color: AppColors.cream),
            ),
            const SizedBox(height: 8),
            Text(
              'Zone 2 session scheduled, two agent tasks completed '
              'overnight, and your weekly review is ready.',
              style: theme.textTheme.bodyMedium
                  ?.copyWith(color: AppColors.cream.withValues(alpha: 0.85)),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Text(
                  'Read digest',
                  style: theme.textTheme.labelLarge
                      ?.copyWith(color: AppColors.cream),
                ),
                const SizedBox(width: 6),
                const Icon(Icons.arrow_forward_rounded,
                    size: 18, color: AppColors.cream),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Tactile dock card: agent tint at low alpha over surface, icon badge,
/// name + tagline. BouncyButton supplies the press feel.
class _AgentCard extends StatelessWidget {
  const _AgentCard({required this.agent, required this.onTap});

  final Agent agent;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return BouncyButton(
      onTap: onTap,
      child: Container(
        width: 170,
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: Color.alphaBlend(
            agent.tint.withValues(alpha: 0.10),
            theme.colorScheme.surface,
          ),
          borderRadius: BorderRadius.circular(AppTheme.radiusCard),
          boxShadow: AppTheme.softShadow(context),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: agent.tint.withValues(alpha: 0.18),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Icon(agent.icon, color: agent.tint, size: 22),
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
