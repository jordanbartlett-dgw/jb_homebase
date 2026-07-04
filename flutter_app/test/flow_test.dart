import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:jb_homebase_app/app.dart';
import 'package:jb_homebase_app/features/chat/widgets/typing_indicator.dart';

/// Drives the core loop end to end against mock data:
/// passkey sign-in → dashboard → agent dock into chat → send → canned
/// reply → agent switch → insights tab. The typing indicator repeats its
/// animation, so fixed-duration pumps are used while it is on screen
/// (pumpAndSettle would never settle).
void main() {
  testWidgets('Sign-in through dashboard, chat, and insights', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: JBHomebaseApp()));
    await tester.pumpAndSettle();

    // Passkey screen → tap through to the dashboard.
    await tester.tap(find.text('Sign in with passkey'));
    await tester.pumpAndSettle();
    expect(find.text('DAILY DIGEST'), findsOneWidget);
    expect(find.text('YOUR AGENTS'), findsOneWidget);

    // Dashboard dock → Workout Coach chat. Content scrolls beneath the
    // floating pill nav, so lift the dock above it before tapping.
    await tester.drag(find.text('YOUR AGENTS'), const Offset(0, -150));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Workout Coach'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Hill repeats today'), findsOneWidget);

    // Send a message; typing indicator shows, canned reply lands ~1.4s
    // later. The list animates a scroll-to-bottom after each append, so
    // give each step a frame pump plus clock for the scroll to finish.
    await tester.enterText(find.byType(TextField), 'Swap today for a run?');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 700));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Swap today for a run?'), findsOneWidget);
    expect(find.byType(TypingIndicator), findsOneWidget);
    await tester.pump(const Duration(milliseconds: 900));
    await tester.pump(const Duration(milliseconds: 900));
    expect(find.byType(TypingIndicator), findsNothing);
    expect(find.textContaining('Mock reply'), findsOneWidget);

    // Switch agents via the picker chips — Claw Main thread appears with
    // its tool-call chip, and the workout thread is preserved in state.
    await tester.tap(find.text('Claw Main'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Pull the SAGE quotes'), findsOneWidget);
    expect(find.textContaining('2 open quotes found'), findsOneWidget);

    // Insights tab via the floating pill nav.
    await tester.tap(find.byIcon(Icons.insights_rounded));
    await tester.pumpAndSettle();
    expect(find.text('Insights'), findsWidgets);
    expect(find.text('TRAINING LOAD'), findsOneWidget);
  });
}
