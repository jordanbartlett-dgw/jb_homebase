import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/skill_info.dart';
import '../../../state/app_state.dart';
import '../../../theme/colors.dart';
import '../../../theme/spacing.dart';

class ContextTab extends ConsumerStatefulWidget {
  const ContextTab({super.key});

  @override
  ConsumerState<ContextTab> createState() => _ContextTabState();
}

class _ContextTabState extends ConsumerState<ContextTab> {
  String? _expandedSkill;

  @override
  Widget build(BuildContext context) {
    final skills = ref.watch(roomSkillsProvider);
    final textTheme = Theme.of(context).textTheme;

    return ListView(
      padding: const EdgeInsets.fromLTRB(
        Spacing.lg,
        Spacing.lg,
        Spacing.lg,
        Spacing.xl,
      ),
      children: [
        _SectionHeader(label: 'Skills (${skills.length})'),
        const SizedBox(height: Spacing.sm),
        Wrap(
          spacing: Spacing.sm,
          runSpacing: Spacing.sm,
          children: [
            for (final skill in skills)
              _SkillChip(
                skill: skill,
                expanded: _expandedSkill == skill.name,
                onTap: () {
                  setState(() {
                    _expandedSkill = _expandedSkill == skill.name ? null : skill.name;
                  });
                },
              ),
          ],
        ),
        const SizedBox(height: Spacing.xl),
        const _SectionHeader(label: 'Memory'),
        const SizedBox(height: Spacing.sm),
        Text('On. Recent conversations, ratings, and Obsidian notes.',
            style: textTheme.bodyMedium),
        const SizedBox(height: Spacing.xl),
        const _SectionHeader(label: 'Sources'),
        const SizedBox(height: Spacing.sm),
        Text('Obsidian vault indexed. SAGE Connect, HubSpot, Notion, Gmail, Findhelp.',
            style: textTheme.bodyMedium),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Text(
      label.toUpperCase(),
      style: Theme.of(context).textTheme.labelSmall,
    );
  }
}

class _SkillChip extends StatelessWidget {
  const _SkillChip({
    required this.skill,
    required this.expanded,
    required this.onTap,
  });

  final SkillInfo skill;
  final bool expanded;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Material(
      color: AppColors.surfaceVariant,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: AnimatedSize(
          duration: const Duration(milliseconds: 150),
          curve: Curves.easeOut,
          alignment: Alignment.topLeft,
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: Spacing.md,
              vertical: Spacing.sm,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(skill.name, style: textTheme.labelLarge),
                if (expanded) ...[
                  const SizedBox(height: Spacing.xs),
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 280),
                    child: Text(skill.description, style: textTheme.bodySmall),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
