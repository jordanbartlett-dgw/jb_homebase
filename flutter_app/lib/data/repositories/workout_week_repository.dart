import '../../shared/api/api_client.dart';
import '../../shared/api/workout_api_models.dart';
import '../../shared/models/workout_week.dart';

class WorkoutWeekRepository {
  const WorkoutWeekRepository(this._apiClient);

  final ApiClient _apiClient;

  Future<WorkoutWeek> fetchWeek() async {
    final payload = await _apiClient.fetchWorkoutWeek();
    return WorkoutWeek(
      weekStart: payload.weekStart,
      weekEnd: payload.weekEnd,
      timezone: payload.timezone,
      planStatus: _planStatus(payload.planStatus),
      days: [for (final day in payload.days) _day(day)],
    );
  }

  WorkoutDay _day(WorkoutDayPayload payload) {
    final planned = payload.planned;
    return WorkoutDay(
      date: payload.date,
      isToday: payload.isToday,
      planned: planned == null
          ? null
          : PlannedSession(
              sessionType: planned.sessionType,
              description: planned.description,
              targets: planned.targets,
            ),
      logs: [
        for (final log in payload.logs)
          LoggedWorkout(
            id: log.id,
            activity: log.activity,
            details: log.details,
            notes: log.notes,
            verdict: _verdict(log.verdict),
            reason: log.reason,
          ),
      ],
      status: _dayStatus(payload.dayStatus),
    );
  }

  PlanStatus _planStatus(String raw) => switch (raw) {
        'active' => PlanStatus.active,
        'ended' => PlanStatus.ended,
        _ => PlanStatus.none,
      };

  DayStatus _dayStatus(String raw) => switch (raw) {
        'logged' => DayStatus.logged,
        'missed' => DayStatus.missed,
        'rest' => DayStatus.rest,
        'upcoming' => DayStatus.upcoming,
        'today' => DayStatus.today,
        _ => DayStatus.empty,
      };

  OverloadVerdict? _verdict(String? raw) => switch (raw) {
        'positive' => OverloadVerdict.positive,
        'none' => OverloadVerdict.none,
        'negative' => OverloadVerdict.negative,
        'no_baseline' => OverloadVerdict.noBaseline,
        _ => null,
      };
}
