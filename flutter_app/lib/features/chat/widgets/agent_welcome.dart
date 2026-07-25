import 'package:flutter/material.dart';

import '../../../shared/models/agent.dart';
import '../../../theme/app_theme.dart';

/// Empty-thread onboarding that can grow with specialized agents.
class AgentWelcome extends StatelessWidget {
  const AgentWelcome({
    super.key,
    required this.agent,
    required this.onSelectPrompt,
  });

  final Agent agent;
  final ValueChanged<String> onSelectPrompt;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final specialized = agent.introduction != null || agent.starterPrompts.isNotEmpty;

    return ListView(
      key: ValueKey('welcome-${agent.id}'),
      padding: AppTheme.pagePadding.copyWith(
        top: specialized ? 28 : 80,
        bottom: 32,
      ),
      children: [
        Align(
          alignment: Alignment.center,
          child: Container(
            width: 58,
            height: 58,
            decoration: BoxDecoration(
              color: agent.tint.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                color: agent.tint.withValues(alpha: 0.28),
              ),
            ),
            child: Icon(agent.icon, size: 29, color: agent.tint),
          ),
        ),
        const SizedBox(height: 18),
        Text(
          specialized ? agent.name : 'Start a conversation with ${agent.name}',
          textAlign: TextAlign.center,
          style: theme.textTheme.headlineSmall,
        ),
        if (agent.introduction case final introduction?) ...[
          const SizedBox(height: 10),
          Text(
            introduction,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyLarge?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              height: 1.5,
            ),
          ),
        ],
        if (agent.caution case final caution?) ...[
          const SizedBox(height: 18),
          Container(
            key: ValueKey('caution-${agent.id}'),
            padding: const EdgeInsets.all(15),
            decoration: BoxDecoration(
              color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.55),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: theme.colorScheme.outlineVariant),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.info_outline_rounded,
                  size: 20,
                  color: agent.tint,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    caution,
                    style: theme.textTheme.bodyMedium?.copyWith(height: 1.45),
                  ),
                ),
              ],
            ),
          ),
        ],
        if (agent.starterPrompts.isNotEmpty) ...[
          const SizedBox(height: 26),
          Text(
            'START A CHECK',
            style: theme.textTheme.titleSmall,
          ),
          const SizedBox(height: 10),
          for (final prompt in agent.starterPrompts)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: OutlinedButton(
                key: ValueKey('starter-${agent.id}-${agent.starterPrompts.indexOf(prompt)}'),
                onPressed: () => onSelectPrompt(prompt),
                style: OutlinedButton.styleFrom(
                  alignment: Alignment.centerLeft,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 14,
                  ),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        prompt,
                        textAlign: TextAlign.left,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Icon(
                      Icons.arrow_forward_rounded,
                      size: 18,
                      color: agent.tint,
                    ),
                  ],
                ),
              ),
            ),
        ],
      ],
    );
  }
}
