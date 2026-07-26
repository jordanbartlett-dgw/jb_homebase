import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../shared/models/today.dart';
import '../../../shared/widgets/app_markdown.dart';
import '../../../theme/app_theme.dart';

class ProactiveArtifactCard extends StatelessWidget {
  const ProactiveArtifactCard({
    super.key,
    required this.artifact,
    required this.onTap,
  });

  final ProactiveArtifact artifact;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final presentation = _presentationFor(artifact.taskType);

    return Material(
      color: theme.colorScheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: theme.colorScheme.outlineVariant),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: theme.colorScheme.primary.withValues(alpha: 0.09),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  presentation.icon,
                  size: 20,
                  color: theme.colorScheme.primary,
                ),
              ),
              const SizedBox(width: 13),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            presentation.label,
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          _compactTime(artifact.createdAt),
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 5),
                    Text(
                      markdownPlainText(artifact.content),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                        height: 1.4,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 6),
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Icon(
                  Icons.chevron_right_rounded,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

Future<void> showProactiveArtifactDetail(
  BuildContext context,
  ProactiveArtifact artifact,
) {
  final presentation = _presentationFor(artifact.taskType);
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    showDragHandle: true,
    backgroundColor: Theme.of(context).colorScheme.surface,
    constraints: const BoxConstraints(maxWidth: 720),
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    builder: (context) => FractionallySizedBox(
      key: const ValueKey('artifact-detail-sheet'),
      heightFactor: 0.84,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 4, 16, 16),
            child: Row(
              children: [
                Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.09),
                    borderRadius: BorderRadius.circular(13),
                  ),
                  child: Icon(
                    presentation.icon,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                ),
                const SizedBox(width: 13),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        presentation.label,
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        DateFormat.yMMMd().add_jm().format(
                          artifact.createdAt.toLocal(),
                        ),
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Close',
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(Icons.close_rounded),
                ),
              ],
            ),
          ),
          Divider(color: Theme.of(context).colorScheme.outlineVariant),
          Expanded(
            child: SingleChildScrollView(
              padding: AppTheme.pagePadding.copyWith(top: 20, bottom: 40),
              child: AppMarkdown(data: artifact.content),
            ),
          ),
        ],
      ),
    ),
  );
}

String _compactTime(DateTime value) {
  final local = value.toLocal();
  final now = DateTime.now();
  final sameDay = local.year == now.year && local.month == now.month && local.day == now.day;
  return sameDay ? DateFormat.jm().format(local) : DateFormat.MMMd().format(local);
}

_ArtifactPresentation _presentationFor(String taskType) {
  return switch (taskType) {
    'memory_flag' => const _ArtifactPresentation(
      label: 'Memory updated',
      icon: Icons.memory_outlined,
    ),
    'event_trigger' => const _ArtifactPresentation(
      label: 'Agent update',
      icon: Icons.inbox_outlined,
    ),
    'calendar_reminder' => const _ArtifactPresentation(
      label: 'Calendar reminder',
      icon: Icons.event_outlined,
    ),
    'care_docs_check' => const _ArtifactPresentation(
      label: 'Care documents',
      icon: Icons.description_outlined,
    ),
    'weekly_training_review' => const _ArtifactPresentation(
      label: 'Training review',
      icon: Icons.directions_run_outlined,
    ),
    'weekly_review' => const _ArtifactPresentation(
      label: 'Weekly review',
      icon: Icons.calendar_view_week_outlined,
    ),
    'daily_scan' => const _ArtifactPresentation(
      label: 'Daily scan',
      icon: Icons.radar_outlined,
    ),
    'reminder' => const _ArtifactPresentation(
      label: 'Reminder',
      icon: Icons.notifications_none_rounded,
    ),
    _ => _ArtifactPresentation(
      label: _humanizeTaskType(taskType),
      icon: Icons.auto_awesome_outlined,
    ),
  };
}

String _humanizeTaskType(String value) {
  if (value.trim().isEmpty) return 'Agent update';
  final words = value.replaceAll('_', ' ').trim();
  return '${words[0].toUpperCase()}${words.substring(1)}';
}

class _ArtifactPresentation {
  const _ArtifactPresentation({
    required this.label,
    required this.icon,
  });

  final String label;
  final IconData icon;
}
