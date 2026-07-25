import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jb_homebase_app/shared/models/message.dart';
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
}
