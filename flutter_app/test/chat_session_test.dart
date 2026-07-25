import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:jb_homebase_app/app.dart';

void main() {
  testWidgets('New chat clears the thread after confirmation', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: JBHomebaseApp()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Sign in with passkey'));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.chat_bubble_outline_rounded));
    await tester.pumpAndSettle();

    expect(find.textContaining('Pull the SAGE quotes'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('new-chat-button')));
    await tester.pumpAndSettle();
    expect(find.text('Start a new chat?'), findsOneWidget);
    expect(
      find.text('This conversation will stay available in History.'),
      findsOneWidget,
    );

    await tester.tap(find.widgetWithText(FilledButton, 'New chat'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Pull the SAGE quotes'), findsNothing);
    expect(
      find.text('Start a conversation with Claw Main'),
      findsOneWidget,
    );
  });
}
