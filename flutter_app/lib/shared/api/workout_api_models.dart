class PlannedSessionPayload {
  const PlannedSessionPayload({
    required this.sessionType,
    required this.description,
    required this.targets,
  });

  factory PlannedSessionPayload.fromJson(Map<String, dynamic> json) {
    return PlannedSessionPayload(
      sessionType: json['session_type'] as String,
      description: json['description'] as String,
      targets: json['targets'] as Map<String, dynamic>? ?? const {},
    );
  }

  final String sessionType;
  final String description;
  final Map<String, dynamic> targets;
}

class LoggedWorkoutPayload {
  const LoggedWorkoutPayload({
    required this.id,
    required this.activity,
    required this.details,
    required this.notes,
    required this.verdict,
    required this.reason,
  });

  factory LoggedWorkoutPayload.fromJson(Map<String, dynamic> json) {
    return LoggedWorkoutPayload(
      id: json['id'] as String,
      activity: json['activity'] as String,
      details: json['details'] as Map<String, dynamic>? ?? const {},
      notes: json['notes'] as String?,
      verdict: json['verdict'] as String?,
      reason: json['reason'] as String?,
    );
  }

  final String id;
  final String activity;
  final Map<String, dynamic> details;
  final String? notes;
  final String? verdict;
  final String? reason;
}

class WorkoutDayPayload {
  const WorkoutDayPayload({
    required this.date,
    required this.isToday,
    required this.planned,
    required this.logs,
    required this.dayStatus,
  });

  factory WorkoutDayPayload.fromJson(Map<String, dynamic> json) {
    final plannedJson = json['planned'] as Map<String, dynamic>?;
    return WorkoutDayPayload(
      date: DateTime.parse(json['date'] as String),
      isToday: json['is_today'] as bool,
      planned: plannedJson == null ? null : PlannedSessionPayload.fromJson(plannedJson),
      logs: [
        for (final log in json['logs'] as List<dynamic>)
          LoggedWorkoutPayload.fromJson(log as Map<String, dynamic>),
      ],
      dayStatus: json['day_status'] as String,
    );
  }

  final DateTime date;
  final bool isToday;
  final PlannedSessionPayload? planned;
  final List<LoggedWorkoutPayload> logs;
  final String dayStatus;
}

class WorkoutWeekPayload {
  const WorkoutWeekPayload({
    required this.weekStart,
    required this.weekEnd,
    required this.timezone,
    required this.planStatus,
    required this.days,
  });

  factory WorkoutWeekPayload.fromJson(Map<String, dynamic> json) {
    return WorkoutWeekPayload(
      weekStart: DateTime.parse(json['week_start'] as String),
      weekEnd: DateTime.parse(json['week_end'] as String),
      timezone: json['timezone'] as String,
      planStatus: json['plan_status'] as String,
      days: [
        for (final day in json['days'] as List<dynamic>)
          WorkoutDayPayload.fromJson(day as Map<String, dynamic>),
      ],
    );
  }

  final DateTime weekStart;
  final DateTime weekEnd;
  final String timezone;
  final String planStatus;
  final List<WorkoutDayPayload> days;
}
