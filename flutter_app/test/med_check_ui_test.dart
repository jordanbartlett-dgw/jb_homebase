import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jb_homebase_app/app.dart';
import 'package:jb_homebase_app/features/chat/widgets/agent_welcome.dart';
import 'package:jb_homebase_app/shared/models/agent.dart';
import 'package:jb_homebase_app/theme/app_theme.dart';

void main() {
  testWidgets('Med Check welcome explains its boundary and offers starter prompts', (tester) async {
    final agent = Agent.byId('med-check');
    String? selectedPrompt;

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: AgentWelcome(
            agent: agent,
            onSelectPrompt: (prompt) => selectedPrompt = prompt,
          ),
        ),
      ),
    );

    expect(find.text('Med Check'), findsOneWidget);
    expect(find.textContaining('not medical clearance'), findsOneWidget);
    expect(find.textContaining('pharmacist and cardiology team'), findsOneWidget);
    expect(find.text('START A CHECK'), findsOneWidget);
    expect(agent.starterPrompts, hasLength(4));

    final starter = find.byKey(const ValueKey('starter-med-check-0'));
    await tester.ensureVisible(starter);
    await tester.tap(starter);

    expect(selectedPrompt, agent.starterPrompts.first);
  });

  test('Med Check is keyed to the production gateway slug', () {
    final agent = Agent.byId('med-check');

    expect(agent.id, 'med-check');
    expect(agent.name, 'Med Check');
    expect(agent.icon, Icons.medication_outlined);
  });

  testWidgets('starter prompt fills the Med Check composer for review', (tester) async {
    final agent = Agent.byId('med-check');

    await tester.pumpWidget(const ProviderScope(child: JBHomebaseApp()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Sign in with passkey'));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.chat_bubble_outline_rounded));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Med Check'));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('new-chat-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'New chat'));
    await tester.pumpAndSettle();

    expect(find.textContaining('not medical clearance'), findsOneWidget);
    final starter = find.byKey(const ValueKey('starter-med-check-0'));
    await tester.drag(
      find.byKey(const ValueKey('welcome-med-check')),
      const Offset(0, -180),
    );
    await tester.pumpAndSettle();
    await tester.tap(starter);
    await tester.pump();

    final composer = tester.widget<TextField>(find.byType(TextField));
    expect(composer.controller?.text, agent.starterPrompts.first);
  });
}
