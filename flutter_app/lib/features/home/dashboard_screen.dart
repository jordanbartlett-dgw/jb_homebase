import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../routing/routes.dart';
import '../../shared/models/agent.dart';
import '../../shared/models/today.dart';
import '../../shared/widgets/bouncy_button.dart';
import '../../shared/widgets/calendar_event_tile.dart';
import '../../shared/widgets/app_markdown.dart';
import '../../shared/widgets/fade_slide_in.dart';
import '../../state/app_state.dart';
import '../../state/today_state.dart';
import '../../theme/app_theme.dart';
import '../../theme/colors.dart';

/// Homebase landing view: server-truth digest, calendar, and agent dock.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  String get _greeting {
    final hour = DateTime.now().hour;
    if (hour < 12) return 'Good morning,\nJordan';
    if (hour < 17) return 'Good afternoon,\nJordan';
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
    final today = ref.watch(todayControllerProvider);

    return SafeArea(
      bottom: false,
      child: RefreshIndicator(
        onRefresh: () => ref.read(todayControllerProvider.notifier).refreshToday(),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: AppTheme.pagePadding.copyWith(top: 24, bottom: 120),
          children: [
            FadeSlideIn(
              child: Text(
                date.toUpperCase(),
                style: theme.textTheme.titleSmall,
              ),
            ),
            const SizedBox(height: 8),
            FadeSlideIn(
              delay: const Duration(milliseconds: 80),
              child: Text(_greeting, style: theme.textTheme.displayLarge),
            ),
            const SizedBox(height: 24),
            ...today.when(
              loading: () => const [
                _LoadingTodayCard(height: 190),
                SizedBox(height: 28),
                _LoadingTodayCard(height: 120),
              ],
              error: (error, _) => [
                _TodayErrorCard(
                  onRetry: () => ref.invalidate(todayControllerProvider),
                ),
              ],
              data: (overview) => [
                FadeSlideIn(
                  delay: const Duration(milliseconds: 160),
                  child: _DigestCard(
                    digest: overview.digest,
                    onTap: overview.digest == null ? null : () => context.push(Routes.digest),
                  ),
                ),
                const SizedBox(height: 28),
                FadeSlideIn(
                  delay: const Duration(milliseconds: 220),
                  child: _UpcomingCalendar(
                    overview: overview,
                    onViewCalendar: () => context.push(Routes.calendar),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 32),
            FadeSlideIn(
              delay: const Duration(milliseconds: 280),
              child: Text(
                'YOUR AGENTS',
                style: theme.textTheme.titleSmall,
              ),
            ),
            const SizedBox(height: 12),
            FadeSlideIn(
              delay: const Duration(milliseconds: 340),
              child: SizedBox(
                height: 160,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  clipBehavior: Clip.none,
                  itemCount: Agent.roster.length,
                  separatorBuilder: (_, _) => const SizedBox(width: 14),
                  itemBuilder: (context, index) => _AgentCard(
                    agent: Agent.roster[index],
                    onTap: () => _openAgent(
                      context,
                      ref,
                      Agent.roster[index],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DigestCard extends StatelessWidget {
  const _DigestCard({
    required this.digest,
    required this.onTap,
  });

  final DailyDigest? digest;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final heroInk = theme.colorScheme.onInverseSurface;
    final heroAccent = isDark ? AppColors.cobalt : AppColors.cobaltBright;

    return Material(
      color: theme.colorScheme.inverseSurface,
      borderRadius: BorderRadius.circular(AppTheme.radiusCard),
      child: InkWell(
        key: const ValueKey('daily-digest-card'),
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppTheme.radiusCard),
        child: Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppTheme.radiusCard),
            border: Border.all(
              color: heroAccent.withValues(alpha: 0.7),
            ),
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
                      color: digest == null ? heroInk.withValues(alpha: 0.4) : heroAccent,
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
                  const Spacer(),
                  if (digest case final value?)
                    Text(
                      DateFormat.jm().format(
                        value.generatedAt.toLocal(),
                      ),
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: heroInk.withValues(alpha: 0.58),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                digest == null ? 'No morning briefing yet' : 'Your morning briefing',
                style: theme.textTheme.headlineSmall?.copyWith(
                  color: heroInk,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                digest == null
                    ? 'The briefing will appear here after its scheduled run.'
                    : markdownPlainText(digest!.content),
                maxLines: digest == null ? 2 : 4,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: heroInk.withValues(alpha: 0.78),
                ),
              ),
              if (digest != null) ...[
                const SizedBox(height: 16),
                Row(
                  children: [
                    Text(
                      'Read full briefing',
                      style: theme.textTheme.labelLarge?.copyWith(
                        color: heroAccent,
                      ),
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
            ],
          ),
        ),
      ),
    );
  }
}

class _UpcomingCalendar extends StatelessWidget {
  const _UpcomingCalendar({
    required this.overview,
    required this.onViewCalendar,
  });

  final TodayOverview overview;
  final VoidCallback onViewCalendar;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final events = overview.upcomingEvents().take(3).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text('UP NEXT', style: theme.textTheme.titleSmall),
            ),
            TextButton(
              key: const ValueKey('view-calendar-button'),
              onPressed: onViewCalendar,
              child: const Text('View calendar'),
            ),
          ],
        ),
        const SizedBox(height: 8),
        if (!overview.calendarAvailable)
          _CompactCalendarState(
            icon: Icons.cloud_off_outlined,
            text: overview.calendarMessage ?? 'Calendar is temporarily unavailable.',
          )
        else if (events.isEmpty)
          const _CompactCalendarState(
            icon: Icons.event_available_outlined,
            text: 'Your calendar is clear for the next seven days.',
          )
        else
          for (final event in events)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: CalendarEventTile(event: event),
            ),
      ],
    );
  }
}

class _CompactCalendarState extends StatelessWidget {
  const _CompactCalendarState({
    required this.icon,
    required this.text,
  });

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(AppTheme.radiusCard),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Row(
        children: [
          Icon(icon, color: theme.colorScheme.primary),
          const SizedBox(width: 12),
          Expanded(
            child: Text(text, style: theme.textTheme.bodyMedium),
          ),
        ],
      ),
    );
  }
}

class _LoadingTodayCard extends StatelessWidget {
  const _LoadingTodayCard({required this.height});

  final double height;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      height: height,
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(AppTheme.radiusCard),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: const Center(child: CircularProgressIndicator()),
    );
  }
}

class _TodayErrorCard extends StatelessWidget {
  const _TodayErrorCard({required this.onRetry});

  final VoidCallback onRetry;

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
          Text(
            'Couldn’t load today’s briefing and calendar.',
            textAlign: TextAlign.center,
            style: theme.textTheme.titleMedium,
          ),
          const SizedBox(height: 12),
          OutlinedButton(
            onPressed: onRetry,
            child: const Text('Try again'),
          ),
        ],
      ),
    );
  }
}

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
                border: Border.all(
                  color: accent.withValues(alpha: 0.28),
                ),
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
