import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jb_homebase_app/shared/models/message.dart';
import 'package:jb_homebase_app/shared/widgets/app_code_block.dart';
import 'package:jb_homebase_app/shared/widgets/app_markdown.dart';
import 'package:jb_homebase_app/shared/widgets/message_bubble.dart';
import 'package:jb_homebase_app/theme/app_theme.dart';

void main() {
  test('markdownPlainText removes formatting while preserving content', () {
    const source = '''
## Today

**Priority:** Ship the app

- Review calendar
- [Open notes](https://example.com)
''';

    expect(
      markdownPlainText(source),
      'Today\n\nPriority: Ship the app\n• Review calendar\n• Open notes',
    );
  });

  testWidgets('assistant bubbles render Markdown instead of raw markers', (tester) async {
    final message = Message(
      id: 'assistant-1',
      role: MessageRole.assistant,
      body: '**Priority:** Ship the app',
      timestamp: DateTime(2026, 7, 25),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: MessageBubble(message: message),
        ),
      ),
    );

    expect(find.byType(MarkdownBody), findsOneWidget);
    expect(find.textContaining('**'), findsNothing);
    expect(find.textContaining('Priority:'), findsOneWidget);
  });

  testWidgets('user bubbles preserve literal text', (tester) async {
    final message = Message(
      id: 'user-1',
      role: MessageRole.user,
      body: '**keep this literal**',
      timestamp: DateTime(2026, 7, 25),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: MessageBubble(message: message),
        ),
      ),
    );

    expect(find.byType(MarkdownBody), findsNothing);
    expect(find.text('**keep this literal**'), findsOneWidget);
  });

  testWidgets('source links invoke the approved URL handler', (tester) async {
    Uri? opened;

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: AppMarkdown(
            data: '[FDA label](https://www.accessdata.fda.gov/example)',
            onOpenLink: (uri) => opened = uri,
          ),
        ),
      ),
    );

    await tester.tap(find.text('FDA label'));
    expect(opened, Uri.parse('https://www.accessdata.fda.gov/example'));
  });

  testWidgets('non-web links are rejected', (tester) async {
    Uri? opened;

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: AppMarkdown(
            data: '[Local file](file:///private/data)',
            onOpenLink: (uri) => opened = uri,
          ),
        ),
      ),
    );

    await tester.tap(find.text('Local file'));
    await tester.pump();

    expect(opened, isNull);
    expect(find.text('Couldn’t open this source.'), findsOneWidget);
  });

  testWidgets('fenced code renders as a labeled, scrollable code card', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(
          body: AppMarkdown(
            data: '''
Here is the generated script:

```python
async def summarize(items):
    return [item["title"] for item in items]
```
''',
          ),
        ),
      ),
    );

    expect(find.byType(AppCodeBlock), findsOneWidget);
    expect(find.text('PYTHON'), findsOneWidget);
    expect(
      tester.widget<AppCodeBlock>(find.byType(AppCodeBlock)).code,
      contains('async def summarize'),
    );
    expect(find.byKey(const Key('app-code-horizontal-scroll')), findsOneWidget);
  });

  testWidgets('code card toggles line wrapping', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(
          body: AppCodeBlock(
            language: 'json',
            code: '{"a_very_long_key": "a very long value"}',
          ),
        ),
      ),
    );

    expect(find.byKey(const Key('app-code-horizontal-scroll')), findsOneWidget);
    await tester.tap(find.byKey(const Key('app-code-wrap')));
    await tester.pump();

    expect(find.byKey(const Key('app-code-horizontal-scroll')), findsNothing);
    expect(find.byTooltip('Scroll lines'), findsOneWidget);
  });

  testWidgets('copy action places the complete code on the clipboard', (tester) async {
    String? clipboardText;
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        clipboardText = (call.arguments as Map<Object?, Object?>)['text'] as String?;
      }
      return null;
    });
    addTearDown(
      () => messenger.setMockMethodCallHandler(SystemChannels.platform, null),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: const Scaffold(
          body: AppCodeBlock(
            language: 'python',
            code: 'print("JB Homebase")',
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('app-code-copy')));
    await tester.pump();

    expect(clipboardText, 'print("JB Homebase")');
    expect(find.text('Code copied.'), findsOneWidget);
    expect(find.byIcon(Icons.check_rounded), findsOneWidget);
  });

  testWidgets('unknown language labels fall back to plain highlighting', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.dark,
        home: const Scaffold(
          body: AppCodeBlock(
            language: 'made-up-language',
            code: 'still safe to render',
          ),
        ),
      ),
    );

    expect(find.text('MADE-UP-LANGUAGE'), findsOneWidget);
    expect(
      tester.widget<AppCodeBlock>(find.byType(AppCodeBlock)).code,
      'still safe to render',
    );
    expect(tester.takeException(), isNull);
  });
}
