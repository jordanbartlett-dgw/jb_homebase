import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:jb_homebase_app/app.dart';
import 'package:jb_homebase_app/features/room/widgets/typing_indicator.dart';

/// Drives the core v1 loop end to end against mock data:
/// passkey sign-in → Today → Claw Main chat → send → canned reply →
/// Context and History tabs. The typing indicator repeats its animation,
/// so fixed-duration pumps are used while it is on screen (pumpAndSettle
/// would never settle).
void main() {
  testWidgets('Sign-in through chat and room tabs', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: JordanClawApp()));
    await tester.pumpAndSettle();

    // Passkey screen → tap through to Today.
    await tester.tap(find.text('Sign in with passkey'));
    await tester.pumpAndSettle();
    expect(find.text('Chat with Claw Main'), findsOneWidget);

    // Today → Claw Main chat via the bottom CTA. The mock conversation
    // includes an in-progress tool-call chip whose indeterminate spinner
    // never settles, so fixed pumps from here on.
    await tester.tap(find.text('Chat with Claw Main'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text('Chat'), findsOneWidget);

    // Send a message; typing indicator shows, canned reply lands ~1.4s later.
    // The chat list animates a scroll-to-bottom after each append, so give
    // each step a frame pump plus enough clock for the scroll to finish.
    await tester.enterText(find.byType(TextField), 'Morning — what is on today?');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 700));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Morning — what is on today?'), findsOneWidget);
    expect(find.byType(TypingIndicator), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 900));
    await tester.pump(const Duration(milliseconds: 900));
    expect(find.byType(TypingIndicator), findsNothing);
    expect(find.textContaining('Mock reply'), findsOneWidget);

    // Context tab (section headers render uppercase).
    await tester.tap(find.text('Context'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text('MEMORY'), findsOneWidget);
    expect(find.text('SKILLS (12)'), findsOneWidget);

    // History tab (date sections render uppercase).
    await tester.tap(find.text('History'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text('TODAY'), findsWidgets);
  });
}
