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

  testWidgets('Today surfaces memory and agent artifacts with full details', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: JBHomebaseApp()));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Sign in with passkey'));
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('UPDATES'),
      350,
      scrollable: find.byType(Scrollable).first,
    );

    expect(find.text('Memory updated'), findsOneWidget);
    expect(find.text('Agent update'), findsOneWidget);
    expect(find.text('Care documents'), findsOneWidget);
    expect(find.byKey(const ValueKey('view-all-updates')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('view-all-updates')));
    await tester.pumpAndSettle();

    expect(find.text('Recent updates'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Training review'),
      250,
      scrollable: find.byType(Scrollable).last,
    );
    expect(find.text('Training review'), findsOneWidget);

    await tester.tap(find.byTooltip('Close'));
    await tester.pumpAndSettle();
    final artifactCard = find.byKey(const ValueKey('artifact-card-0'));
    final dashboardScroll = find.byType(Scrollable).first;
    await tester.scrollUntilVisible(
      artifactCard,
      180,
      scrollable: dashboardScroll,
    );
    final cardCenter = tester.getCenter(artifactCard);
    await tester.drag(
      dashboardScroll,
      Offset(0, 300 - cardCenter.dy),
    );
    await tester.pumpAndSettle();
    await tester.tap(artifactCard);
    await tester.pumpAndSettle();

    final detailSheet = find.byKey(
      const ValueKey('artifact-detail-sheet'),
    );
    expect(detailSheet, findsOneWidget);
    expect(find.text('Memory updated'), findsWidgets);
    expect(
      find.descendant(
        of: detailSheet,
        matching: find.textContaining(
          'The vendor committed to a 36-hour lead time.',
        ),
      ),
      findsOneWidget,
    );
  });
}
