import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jb_homebase_app/features/home/week_schedule_screen.dart';
import 'package:jb_homebase_app/shared/models/workout_week.dart';
import 'package:jb_homebase_app/state/workout_week_state.dart';

/// Frozen fixture so the test is deterministic on any calendar day,
/// including Monday (when `MockData.workoutWeek`'s `weekStart == today`
/// and no day is `isBefore(today)`, so it renders zero logged days).
final _fixedWeek = WorkoutWeek(
  weekStart: DateTime(2026, 8, 3),
  weekEnd: DateTime(2026, 8, 9),
  timezone: 'America/Chicago',
  planStatus: PlanStatus.active,
  days: [
    WorkoutDay(
      date: DateTime(2026, 8, 3),
      isToday: false,
      planned: const PlannedSession(
        sessionType: 'run',
        description: 'Easy run, 3 mi',
        targets: {},
      ),
      logs: const [
        LoggedWorkout(
          id: 'fixture-log-0',
          activity: 'run',
          details: {'distance_mi': 3.4, 'duration_min': 32},
          notes: 'Felt strong.',
          verdict: OverloadVerdict.positive,
          reason: '+0.4 mi at same pace vs last week',
        ),
      ],
      status: DayStatus.logged,
    ),
    WorkoutDay(
      date: DateTime(2026, 8, 4),
      isToday: false,
      planned: const PlannedSession(
        sessionType: 'strength',
        description: 'Lower body',
        targets: {},
      ),
      logs: const [],
      status: DayStatus.missed,
    ),
    WorkoutDay(
      date: DateTime(2026, 8, 5),
      isToday: false,
      planned: const PlannedSession(
        sessionType: 'rest',
        description: 'Rest day',
        targets: {},
      ),
      logs: const [],
      status: DayStatus.rest,
    ),
    WorkoutDay(
      date: DateTime(2026, 8, 6),
      isToday: true,
      planned: const PlannedSession(
        sessionType: 'run',
        description: 'Tempo run',
        targets: {},
      ),
      logs: const [],
      status: DayStatus.today,
    ),
    WorkoutDay(
      date: DateTime(2026, 8, 7),
      isToday: false,
      planned: const PlannedSession(
        sessionType: 'strength',
        description: 'Upper body',
        targets: {},
      ),
      logs: const [],
      status: DayStatus.upcoming,
    ),
    WorkoutDay(
      date: DateTime(2026, 8, 8),
      isToday: false,
      planned: null,
      logs: const [],
      status: DayStatus.upcoming,
    ),
    WorkoutDay(
      date: DateTime(2026, 8, 9),
      isToday: false,
      planned: null,
      logs: const [],
      status: DayStatus.empty,
    ),
  ],
);

/// Overrides `WorkoutWeekController.build()` to return the frozen fixture
/// instead of `MockData.workoutWeek`, so the test never depends on the real
/// calendar date.
class _FixedWorkoutWeekController extends WorkoutWeekController {
  @override
  Future<WorkoutWeek> build() async => _fixedWeek;
}

void main() {
  testWidgets('renders 7 day tiles from a frozen week fixture', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          workoutWeekControllerProvider.overrideWith(_FixedWorkoutWeekController.new),
        ],
        child: const MaterialApp(home: WeekScheduleScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(_fixedWeek.days, hasLength(7));
    final scrollable = find.byType(Scrollable).first;
    for (final day in _fixedWeek.days) {
      final tileFinder = find.byKey(ValueKey(
        'day-tile-${day.date.toIso8601String().substring(0, 10)}',
      ));
      await tester.scrollUntilVisible(tileFinder, 200, scrollable: scrollable);
      expect(tileFinder, findsOneWidget);

      // The fixture's first day is logged with a positive verdict; assert
      // its verdict line while the tile is still on screen (the ListView
      // is lazy, so tiles scrolled past are disposed and no longer findable
      // once we've moved on to later days).
      if (day.logs.isNotEmpty) {
        expect(
          find.descendant(of: tileFinder, matching: find.textContaining('Overload')),
          findsOneWidget,
        );
      }
    }
  });
}
