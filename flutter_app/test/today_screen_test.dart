import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:jb_homebase_app/app.dart';

void main() {
  testWidgets('Today opens the full digest and seven-day calendar', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: JBHomebaseApp()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Sign in with passkey'));
    await tester.pumpAndSettle();

    expect(find.text('DAILY DIGEST'), findsOneWidget);
    expect(find.text('Your morning briefing'), findsOneWidget);
    expect(find.text('UP NEXT'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('daily-digest-card')));
    await tester.pumpAndSettle();
    expect(find.text('Morning briefing'), findsOneWidget);
    expect(
      find.textContaining('Your board call is at 10:00 AM'),
      findsOneWidget,
    );

    await tester.tap(find.byIcon(Icons.arrow_back_rounded));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('view-calendar-button')));
    await tester.pumpAndSettle();

    expect(find.text('Your Fastmail agenda'), findsOneWidget);
    expect(find.text('FG board call'), findsOneWidget);
    expect(find.text('Zoom'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Ask Claw about your calendar'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.text('Ask Claw about your calendar'), findsOneWidget);
  });
}
