import 'package:flutter/material.dart';

import '../../../shared/widgets/app_markdown.dart';
import '../../../theme/app_theme.dart';
import 'typing_indicator.dart';

/// Ephemeral assistant response shown only while the live stream is active.
class StreamingResponse extends StatelessWidget {
  const StreamingResponse({
    super.key,
    required this.status,
    required this.partialText,
  });

  final String status;
  final String partialText;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final visibleStatus = status.isEmpty ? 'Working' : status;

    if (partialText.isEmpty) {
      return TypingIndicator(
        tint: theme.colorScheme.primary,
        label: visibleStatus,
      );
    }

    final width = MediaQuery.sizeOf(context).width;
    final maxWidth = (width * 0.90).clamp(0.0, 720.0);
    return Semantics(
      liveRegion: true,
      label: '$visibleStatus. Response in progress.',
      child: Align(
        alignment: Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: maxWidth),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(left: 4, top: 5, bottom: 6),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      width: 12,
                      height: 12,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: theme.colorScheme.primary,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      visibleStatus,
                      key: const ValueKey('stream-status-label'),
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              Container(
                key: const ValueKey('streaming-response-bubble'),
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: BoxDecoration(
                  color: theme.colorScheme.surface,
                  border: Border.all(
                    color: theme.colorScheme.primary.withValues(alpha: 0.35),
                  ),
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(AppTheme.radiusBubble),
                    topRight: Radius.circular(AppTheme.radiusBubble),
                    bottomRight: Radius.circular(AppTheme.radiusBubble),
                    bottomLeft: Radius.circular(4),
                  ),
                ),
                child: AppMarkdown(
                  data: partialText,
                  color: theme.colorScheme.onSurface,
                  compact: true,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
