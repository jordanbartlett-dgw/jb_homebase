import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../state/app_state.dart';
import '../../theme/spacing.dart';

/// Voice preview — transcript + audio scrubber + Send/Discard/Re-record.
///
/// Preview-before-send is the v1 default (PRD). Auto-send-on-stop is a
/// v1.1 setting.
class VoicePreview extends ConsumerWidget {
  const VoicePreview({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final textTheme = theme.textTheme;
    final activeAgent = ref.watch(activeAgentProvider);

    const placeholderTranscript =
        'Just got off the call with the vendor. They want forty-eight hours on the lead '
        'time but I think we can push for thirty-six. Remind me to follow up tomorrow '
        'morning before the FG board prep.';

    return Scaffold(
      appBar: AppBar(
        title: Text('Voice preview', style: textTheme.titleMedium),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: () => context.pop(),
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.all(Spacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Transcript', style: textTheme.labelSmall),
            const SizedBox(height: Spacing.sm),
            Container(
              padding: const EdgeInsets.all(Spacing.lg),
              decoration: BoxDecoration(
                color: theme.colorScheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: theme.colorScheme.outlineVariant,
                ),
              ),
              child: Text(placeholderTranscript, style: textTheme.bodyLarge),
            ),
            const SizedBox(height: Spacing.xl),
            Text('Audio', style: textTheme.labelSmall),
            const SizedBox(height: Spacing.sm),
            const _AudioScrubberStub(),
            const Spacer(),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => context.pop(),
                    child: const Text('Discard'),
                  ),
                ),
                const SizedBox(width: Spacing.md),
                Expanded(
                  child: OutlinedButton(
                    onPressed: () {
                      // Pop preview, go back to voice overlay.
                      context.pop();
                      context.push(Routes.voice);
                    },
                    child: const Text('Re-record'),
                  ),
                ),
                const SizedBox(width: Spacing.md),
                Expanded(
                  child: FilledButton(
                    onPressed: () {
                      // TODO(backend): multipart POST audio + transcript to
                      // /api/agents/:agentId/voice. For now, append a stub
                      // user message and jump into the chat.
                      ref
                          .read(agentThreadProvider(activeAgent.id).notifier)
                          .appendUserMessage('[voice] $placeholderTranscript');
                      context.go(Routes.agents);
                    },
                    child: const Text('Send'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _AudioScrubberStub extends StatelessWidget {
  const _AudioScrubberStub();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final textTheme = theme.textTheme;
    return Container(
      padding: const EdgeInsets.all(Spacing.md),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Row(
        children: [
          Icon(Icons.play_arrow, color: theme.colorScheme.primary),
          const SizedBox(width: Spacing.sm),
          Expanded(
            child: Container(
              height: 4,
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(width: Spacing.sm),
          Text('0:08', style: textTheme.bodySmall),
        ],
      ),
    );
  }
}
