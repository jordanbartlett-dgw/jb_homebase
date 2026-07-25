import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../state/today_state.dart';
import '../../theme/app_theme.dart';

class DigestDetailScreen extends ConsumerWidget {
  const DigestDetailScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final today = ref.watch(todayControllerProvider);
    final theme = Theme.of(context);

    return SafeArea(
      child: Column(
        children: [
          Padding(
            padding: AppTheme.pagePadding.copyWith(top: 10, bottom: 10),
            child: Row(
              children: [
                IconButton(
                  tooltip: 'Back to Home',
                  onPressed: context.pop,
                  icon: const Icon(Icons.arrow_back_rounded),
                ),
                const SizedBox(width: 4),
                Expanded(
                  child: Text(
                    'Daily Digest',
                    style: theme.textTheme.titleLarge,
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: today.when(
              loading: () => const Center(
                child: CircularProgressIndicator(),
              ),
              error: (error, _) => _DigestError(
                onRetry: () => ref.invalidate(todayControllerProvider),
              ),
              data: (overview) {
                final digest = overview.digest;
                if (digest == null) {
                  return const _NoDigest();
                }
                return ListView(
                  padding: AppTheme.pagePadding.copyWith(
                    top: 24,
                    bottom: 120,
                  ),
                  children: [
                    Text(
                      DateFormat('EEEE, MMMM d').format(overview.date),
                      style: theme.textTheme.titleSmall,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Morning briefing',
                      style: theme.textTheme.displayMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Generated ${DateFormat.jm().format(digest.generatedAt.toLocal())}',
                      style: theme.textTheme.bodySmall,
                    ),
                    const SizedBox(height: 28),
                    SelectableText(
                      digest.content,
                      style: theme.textTheme.bodyLarge?.copyWith(height: 1.6),
                    ),
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

class _NoDigest extends StatelessWidget {
  const _NoDigest();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: AppTheme.pagePadding,
        child: Text(
          'No morning briefing has been generated today.',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.titleMedium,
        ),
      ),
    );
  }
}

class _DigestError extends StatelessWidget {
  const _DigestError({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: OutlinedButton(
        onPressed: onRetry,
        child: const Text('Try loading again'),
      ),
    );
  }
}
