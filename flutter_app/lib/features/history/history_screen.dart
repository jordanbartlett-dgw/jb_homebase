import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../routing/routes.dart';
import '../../shared/models/agent.dart';
import '../../shared/models/conversation.dart';
import '../../shared/widgets/fade_slide_in.dart';
import '../../state/conversation_state.dart';
import '../../theme/app_theme.dart';

class HistoryScreen extends ConsumerWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = ref.watch(conversationHistoryProvider);
    final theme = Theme.of(context);

    return SafeArea(
      bottom: false,
      child: RefreshIndicator(
        onRefresh: () => ref.read(conversationHistoryProvider.notifier).refreshHistory(),
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverPadding(
              padding: AppTheme.pagePadding.copyWith(top: 24),
              sliver: SliverToBoxAdapter(
                child: FadeSlideIn(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('History', style: theme.textTheme.displayMedium),
                      const SizedBox(height: 6),
                      Text(
                        'Your conversations, kept by session.',
                        style: theme.textTheme.bodyMedium,
                      ),
                    ],
                  ),
                ),
              ),
            ),
            history.when(
              loading: () => const SliverFillRemaining(
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (error, _) => SliverFillRemaining(
                child: _HistoryError(
                  onRetry: () => ref.invalidate(conversationHistoryProvider),
                ),
              ),
              data: (conversations) {
                if (conversations.isEmpty) {
                  return const SliverFillRemaining(
                    hasScrollBody: false,
                    child: _EmptyHistory(),
                  );
                }
                return SliverPadding(
                  padding: AppTheme.pagePadding.copyWith(
                    top: 24,
                    bottom: 120,
                  ),
                  sliver: SliverList.list(
                    children: [
                      ..._groupedConversationTiles(context, conversations),
                      if (ref.read(conversationHistoryProvider.notifier).hasMore)
                        Padding(
                          padding: const EdgeInsets.only(top: 12),
                          child: OutlinedButton(
                            onPressed: () => ref
                                .read(
                                  conversationHistoryProvider.notifier,
                                )
                                .loadMore(),
                            child: const Text('Load older conversations'),
                          ),
                        ),
                    ],
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _groupedConversationTiles(
    BuildContext context,
    List<ConversationSummary> conversations,
  ) {
    final widgets = <Widget>[];
    String? currentGroup;
    for (final conversation in conversations) {
      final group = _dateGroup(conversation.lastMessageAt);
      if (group != currentGroup) {
        if (widgets.isNotEmpty) widgets.add(const SizedBox(height: 22));
        widgets.add(
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Text(
              group.toUpperCase(),
              style: Theme.of(context).textTheme.titleSmall,
            ),
          ),
        );
        currentGroup = group;
      }
      widgets.add(
        Padding(
          padding: const EdgeInsets.only(bottom: 10),
          child: _ConversationTile(
            conversation: conversation,
            onTap: () => context.push(
              Routes.historyDetail(conversation.id),
            ),
          ),
        ),
      );
    }
    return widgets;
  }

  String _dateGroup(DateTime timestamp) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final local = timestamp.toLocal();
    final day = DateTime(local.year, local.month, local.day);
    if (day == today) return 'Today';
    if (day.isAfter(today.subtract(const Duration(days: 7)))) {
      return 'Previous 7 days';
    }
    return 'Older';
  }
}

class _ConversationTile extends StatelessWidget {
  const _ConversationTile({
    required this.conversation,
    required this.onTap,
  });

  final ConversationSummary conversation;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final agent = Agent.byId(conversation.agentSlug);
    final localTime = conversation.lastMessageAt.toLocal();
    final when = DateUtils.isSameDay(localTime, DateTime.now())
        ? DateFormat.jm().format(localTime)
        : DateFormat('MMM d').format(localTime);

    return Material(
      color: theme.colorScheme.surface,
      borderRadius: BorderRadius.circular(AppTheme.radiusCard),
      child: InkWell(
        key: ValueKey(conversation.id),
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppTheme.radiusCard),
        child: Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppTheme.radiusCard),
            border: Border.all(color: theme.colorScheme.outlineVariant),
          ),
          child: Row(
            children: [
              Container(
                width: 42,
                height: 42,
                decoration: BoxDecoration(
                  color: agent.tint.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(agent.icon, color: agent.tint, size: 21),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            conversation.title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.titleMedium,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(when, style: theme.textTheme.bodySmall),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        Text(agent.name, style: theme.textTheme.bodySmall),
                        Text(
                          '  ·  ${conversation.messageCount} messages',
                          style: theme.textTheme.bodySmall,
                        ),
                        if (conversation.isActive) ...[
                          const SizedBox(width: 8),
                          Container(
                            width: 6,
                            height: 6,
                            decoration: BoxDecoration(
                              color: theme.colorScheme.primary,
                              shape: BoxShape.circle,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 6),
              const Icon(Icons.chevron_right_rounded),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmptyHistory extends StatelessWidget {
  const _EmptyHistory();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: AppTheme.pagePadding,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.forum_outlined,
              size: 40,
              color: Theme.of(context).colorScheme.primary,
            ),
            const SizedBox(height: 14),
            Text(
              'No conversations yet',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 6),
            Text(
              'Messages with your agents will appear here.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ],
        ),
      ),
    );
  }
}

class _HistoryError extends StatelessWidget {
  const _HistoryError({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('Couldn’t load conversation history.'),
          const SizedBox(height: 12),
          OutlinedButton(onPressed: onRetry, child: const Text('Try again')),
        ],
      ),
    );
  }
}
