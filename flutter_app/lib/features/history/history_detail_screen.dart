import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../shared/models/agent.dart';
import '../../shared/widgets/message_bubble.dart';
import '../../state/conversation_state.dart';
import '../../theme/app_theme.dart';

class HistoryDetailScreen extends ConsumerWidget {
  const HistoryDetailScreen({
    super.key,
    required this.conversationId,
  });

  final String conversationId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(conversationDetailProvider(conversationId));

    return SafeArea(
      child: Column(
        children: [
          Padding(
            padding: AppTheme.pagePadding.copyWith(top: 10, bottom: 10),
            child: Row(
              children: [
                IconButton(
                  tooltip: 'Back to history',
                  onPressed: context.pop,
                  icon: const Icon(Icons.arrow_back_rounded),
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: Text(
                    'Conversation',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                Text(
                  'READ ONLY',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: detail.when(
              loading: () => const Center(
                child: CircularProgressIndicator(),
              ),
              error: (error, _) => Center(
                child: OutlinedButton(
                  onPressed: () => ref.invalidate(
                    conversationDetailProvider(conversationId),
                  ),
                  child: const Text('Try loading again'),
                ),
              ),
              data: (value) {
                final agent = Agent.byId(value.conversation.agentSlug);
                return ListView(
                  padding: AppTheme.pagePadding.copyWith(
                    top: 18,
                    bottom: 120,
                  ),
                  children: [
                    Text(
                      value.conversation.title,
                      style: Theme.of(context).textTheme.headlineSmall,
                    ),
                    const SizedBox(height: 6),
                    Text(
                      '${agent.name} · '
                      '${DateFormat.yMMMd().add_jm().format(value.conversation.createdAt.toLocal())}',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 20),
                    for (final message in value.messages) MessageBubble(message: message),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
