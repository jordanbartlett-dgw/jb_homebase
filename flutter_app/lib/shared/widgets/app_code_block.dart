import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_highlighting/flutter_highlighting.dart';
import 'package:flutter_highlighting/themes/github-dark.dart';
import 'package:flutter_highlighting/themes/github.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:highlighting/languages/all.dart';
import 'package:markdown/markdown.dart' as md;

/// Branded, non-executable presentation for fenced Markdown code.
///
/// Code is always treated as text. Copying is the only action that moves it
/// outside the renderer; execution stays on the gateway's sandboxed Code Mode
/// surface.
class AppCodeBlock extends StatefulWidget {
  const AppCodeBlock({
    super.key,
    required this.code,
    this.language,
  });

  final String code;
  final String? language;

  @override
  State<AppCodeBlock> createState() => _AppCodeBlockState();
}

class _AppCodeBlockState extends State<AppCodeBlock> {
  Timer? _copiedTimer;
  bool _copied = false;
  bool _wrapLines = false;

  @override
  void dispose() {
    _copiedTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;
    final language = _languageLabel(widget.language);
    final code = HighlightView(
      widget.code,
      languageId: _highlightLanguage(widget.language),
      theme: _syntaxTheme(isDark),
      padding: const EdgeInsets.all(14),
      textStyle: theme.textTheme.bodyMedium?.copyWith(
        fontFamily: 'monospace',
        fontSize: 13,
        height: 1.55,
      ),
      tabSize: 2,
    );

    return Container(
      key: const Key('app-code-block'),
      width: double.infinity,
      margin: const EdgeInsets.symmetric(vertical: 6),
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        border: Border.all(color: scheme.outlineVariant),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            constraints: const BoxConstraints(minHeight: 42),
            padding: const EdgeInsets.only(left: 12, right: 4),
            decoration: BoxDecoration(
              color: scheme.surface,
              border: Border(
                bottom: BorderSide(color: scheme.outlineVariant),
              ),
            ),
            child: Row(
              children: [
                Icon(
                  Icons.code_rounded,
                  size: 17,
                  color: scheme.primary,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    language,
                    key: const Key('app-code-language'),
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: scheme.primary,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.45,
                    ),
                  ),
                ),
                IconButton(
                  key: const Key('app-code-wrap'),
                  tooltip: _wrapLines ? 'Scroll lines' : 'Wrap lines',
                  visualDensity: VisualDensity.compact,
                  onPressed: () => setState(() => _wrapLines = !_wrapLines),
                  icon: Icon(
                    _wrapLines ? Icons.wrap_text_rounded : Icons.segment_rounded,
                    size: 19,
                  ),
                ),
                IconButton(
                  key: const Key('app-code-copy'),
                  tooltip: _copied ? 'Copied' : 'Copy code',
                  visualDensity: VisualDensity.compact,
                  onPressed: _copyCode,
                  icon: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 160),
                    child: Icon(
                      _copied ? Icons.check_rounded : Icons.content_copy_rounded,
                      key: ValueKey(_copied),
                      size: 18,
                      color: _copied ? scheme.primary : scheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (_wrapLines)
            code
          else
            SingleChildScrollView(
              key: const Key('app-code-horizontal-scroll'),
              scrollDirection: Axis.horizontal,
              child: code,
            ),
        ],
      ),
    );
  }

  Future<void> _copyCode() async {
    await Clipboard.setData(ClipboardData(text: widget.code));
    if (!mounted) return;

    _copiedTimer?.cancel();
    setState(() => _copied = true);
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        const SnackBar(
          content: Text('Code copied.'),
          duration: Duration(seconds: 2),
        ),
      );
    _copiedTimer = Timer(const Duration(seconds: 2), () {
      if (mounted) setState(() => _copied = false);
    });
  }
}

/// Replaces fenced Markdown `<pre>` nodes with [AppCodeBlock].
class AppCodeBlockMarkdownBuilder extends MarkdownElementBuilder {
  @override
  bool isBlockElement() => true;

  @override
  Widget? visitElementAfterWithContext(
    BuildContext context,
    md.Element element,
    TextStyle? preferredStyle,
    TextStyle? parentStyle,
  ) {
    final codeElement = element.children
        ?.whereType<md.Element>()
        .where((child) => child.tag == 'code')
        .firstOrNull;
    final languageClass = codeElement?.attributes['class'];
    final language = languageClass?.startsWith('language-') ?? false
        ? languageClass!.substring('language-'.length)
        : null;
    final source = _nodeText(codeElement ?? element).replaceFirst(
      RegExp(r'\n$'),
      '',
    );

    return AppCodeBlock(code: source, language: language);
  }
}

String _nodeText(md.Node node) {
  return switch (node) {
    md.Text(:final text) => text,
    md.Element(:final children) => children?.map(_nodeText).join() ?? '',
    _ => '',
  };
}

Map<String, TextStyle> _syntaxTheme(bool isDark) {
  final source = isDark ? githubDarkTheme : githubTheme;
  return {
    ...source,
    'root': source['root']!.copyWith(backgroundColor: Colors.transparent),
  };
}

String _languageLabel(String? language) {
  final normalized = language?.trim();
  return normalized == null || normalized.isEmpty ? 'CODE' : normalized.toUpperCase();
}

String _highlightLanguage(String? language) {
  final normalized = (language ?? '').trim().toLowerCase();
  final candidate =
      const {
        'c#': 'csharp',
        'cs': 'csharp',
        'html': 'xml',
        'htm': 'xml',
        'js': 'javascript',
        'jsx': 'javascript',
        'md': 'markdown',
        'py': 'python',
        'sh': 'bash',
        'shell': 'bash',
        'text': 'plaintext',
        'ts': 'typescript',
        'tsx': 'typescript',
        'txt': 'plaintext',
        'yml': 'yaml',
      }[normalized] ??
      normalized;
  return allLanguages.containsKey(candidate) ? candidate : 'plaintext';
}
