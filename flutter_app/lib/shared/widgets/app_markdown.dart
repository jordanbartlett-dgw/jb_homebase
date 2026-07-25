import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

/// Branded Markdown renderer for agent output and long-form app content.
class AppMarkdown extends StatelessWidget {
  const AppMarkdown({
    super.key,
    required this.data,
    this.color,
    this.selectable = true,
    this.compact = false,
  });

  final String data;
  final Color? color;
  final bool selectable;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final body = theme.textTheme.bodyLarge?.copyWith(
      color: color ?? scheme.onSurface,
      height: compact ? 1.35 : 1.55,
    );
    final code = theme.textTheme.bodyMedium?.copyWith(
      color: color ?? scheme.onSurface,
      fontFamily: 'monospace',
      backgroundColor: scheme.surfaceContainerHighest,
    );

    return MarkdownBody(
      data: data,
      selectable: selectable,
      styleSheet: MarkdownStyleSheet.fromTheme(theme).copyWith(
        p: body,
        strong: body?.copyWith(fontWeight: FontWeight.w700),
        em: body?.copyWith(fontStyle: FontStyle.italic),
        h1: theme.textTheme.headlineMedium?.copyWith(color: color),
        h2: theme.textTheme.headlineSmall?.copyWith(color: color),
        h3: theme.textTheme.titleLarge?.copyWith(color: color),
        listBullet: body?.copyWith(color: scheme.primary),
        blockquote: body?.copyWith(
          color: (color ?? scheme.onSurface).withValues(alpha: 0.76),
          fontStyle: FontStyle.italic,
        ),
        blockquotePadding: const EdgeInsets.fromLTRB(14, 8, 12, 8),
        blockquoteDecoration: BoxDecoration(
          color: scheme.primary.withValues(alpha: 0.07),
          border: Border(
            left: BorderSide(color: scheme.primary, width: 3),
          ),
        ),
        code: code,
        codeblockDecoration: BoxDecoration(
          color: scheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(10),
        ),
        codeblockPadding: const EdgeInsets.all(12),
        a: body?.copyWith(
          color: scheme.primary,
          decoration: TextDecoration.underline,
          decorationColor: scheme.primary,
        ),
        horizontalRuleDecoration: BoxDecoration(
          border: Border(
            top: BorderSide(color: scheme.outlineVariant),
          ),
        ),
        pPadding: EdgeInsets.only(bottom: compact ? 4 : 10),
        h1Padding: const EdgeInsets.only(top: 8, bottom: 8),
        h2Padding: const EdgeInsets.only(top: 8, bottom: 6),
        h3Padding: const EdgeInsets.only(top: 6, bottom: 4),
        listIndent: 22,
      ),
    );
  }
}

/// Removes common Markdown markers for constrained, ellipsized previews.
String markdownPlainText(String source) {
  return source
      .replaceAll(RegExp(r'```[a-zA-Z0-9_-]*\n?'), '')
      .replaceAll('```', '')
      .replaceAllMapped(
        RegExp(r'!\[([^\]]*)\]\([^)]+\)'),
        (match) => match.group(1) ?? '',
      )
      .replaceAllMapped(
        RegExp(r'\[([^\]]+)\]\([^)]+\)'),
        (match) => match.group(1) ?? '',
      )
      .replaceAll(RegExp(r'^\s{0,3}#{1,6}\s+', multiLine: true), '')
      .replaceAll(RegExp(r'^\s*>\s?', multiLine: true), '')
      .replaceAll(RegExp(r'^\s*[-*+]\s+', multiLine: true), '• ')
      .replaceAll(RegExp(r'[*_~`]'), '')
      .replaceAll(RegExp(r'\n{3,}'), '\n\n')
      .trim();
}
