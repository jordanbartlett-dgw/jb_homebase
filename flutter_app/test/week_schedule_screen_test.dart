import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jb_homebase_app/features/home/week_schedule_screen.dart';
import 'package:jb_homebase_app/shared/api/mock_data.dart';

void main() {
  testWidgets('renders 7 day tiles from the mock week', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: WeekScheduleScreen()),
      ),
    );
    await tester.pumpAndSettle();

    // Mock mode is the default in tests (GatewayConfig.isLive is false).
    final week = MockData.workoutWeek;
    expect(week.days, hasLength(7));
    final scrollable = find.byType(Scrollable).first;
    for (final day in week.days) {
      final tileFinder = find.byKey(ValueKey(
        'day-tile-${day.date.toIso8601String().substring(0, 10)}',
      ));
      await tester.scrollUntilVisible(tileFinder, 200, scrollable: scrollable);
      expect(tileFinder, findsOneWidget);
    }

    // At least one logged day shows a verdict line.
    expect(find.textContaining('Overload'), findsWidgets);
  });
}
