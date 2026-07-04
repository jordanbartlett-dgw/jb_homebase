import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../state/app_state.dart';
import '../../../theme/colors.dart';
import '../../../theme/spacing.dart';
import '../models/conversation.dart';

/// Past conversations grouped by date band: Today / Yesterday / This Week / Earlier.
class HistoryTab extends ConsumerWidget {
  const HistoryTab({super.key});

  String _bandFor(DateTime ts) {
    final now = DateTime(2026, 5, 22, 8, 15);
    final today = DateTime(now.year, now.month, now.day);
    final yesterday = today.subtract(const Duration(days: 1));
    final weekAgo = today.subtract(const Duration(days: 7));
    final tsDate = DateTime(ts.year, ts.month, ts.day);

    if (tsDate == today) return 'Today';
    if (tsDate == yesterday) return 'Yesterday';
    if (tsDate.isAfter(weekAgo)) return 'This week';
    return 'Earlier';
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = ref.watch(roomHistoryProvider);

    // Group preserving order: Today, Yesterday, This week, Earlier.
    final bands = <String, List<Conversation>>{
      'Today': [],
      'Yesterday': [],
      'This week': [],
      'Earlier': [],
    };
    for (final conv in history) {
      bands[_bandFor(conv.startedAt)]?.add(conv);
    }

    return ListView(
      padding: const EdgeInsets.fromLTRB(
        Spacing.lg,
        Spacing.lg,
        Spacing.lg,
        Spacing.xl,
      ),
      children: [
        for (final entry in bands.entries)
          if (entry.value.isNotEmpty) ...[
            Padding(
              padding: const EdgeInsets.only(top: Spacing.md, bottom: Spacing.sm),
              child: Text(
                entry.key.toUpperCase(),
                style: Theme.of(context).textTheme.labelSmall,
              ),
            ),
            for (final conv in entry.value) _HistoryRow(conversation: conv),
          ],
      ],
    );
  }
}

class _HistoryRow extends StatelessWidget {
  const _HistoryRow({required this.conversation});
  final Conversation conversation;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final time = TimeOfDay.fromDateTime(conversation.startedAt).format(context);

    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => _showReadOnly(context, conversation),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: Spacing.md,
            vertical: Spacing.md,
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      conversation.preview,
                      style: textTheme.bodyLarge,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${conversation.messageCount} messages, $time',
                      style: textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: AppColors.textMuted),
            ],
          ),
        ),
      ),
    );
  }
}

void _showReadOnly(BuildContext context, Conversation conv) {
  Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (context) => _ReadOnlyConversationScreen(conversation: conv),
    ),
  );
}

class _ReadOnlyConversationScreen extends StatelessWidget {
  const _ReadOnlyConversationScreen({required this.conversation});
  final Conversation conversation;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Scaffold(
      appBar: AppBar(title: Text(conversation.preview)),
      body: Padding(
        padding: const EdgeInsets.all(Spacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${conversation.messageCount} messages',
              style: textTheme.bodySmall,
            ),
            const SizedBox(height: Spacing.lg),
            Text(
              'Read-only mock view. Tap below to continue this thread in a new conversation.',
              style: textTheme.bodyMedium,
            ),
            const Spacer(),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () {
                  // TODO(backend): seed a new conversation with this thread's context.
                  Navigator.of(context).pop();
                },
                child: const Text('Continue this thread'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
