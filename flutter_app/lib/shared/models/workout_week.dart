import 'package:flutter/foundation.dart';

enum OverloadVerdict { positive, none, negative, noBaseline }

enum DayStatus { logged, missed, rest, upcoming, today, empty }

enum PlanStatus { active, none, ended }

@immutable
class PlannedSession {
  const PlannedSession({
    required this.sessionType,
    required this.description,
    required this.targets,
  });

  final String sessionType;
  final String description;
  final Map<String, dynamic> targets;
}

@immutable
class LoggedWorkout {
  const LoggedWorkout({
    required this.id,
    required this.activity,
    required this.details,
    required this.notes,
    required this.verdict,
    required this.reason,
  });

  final String id;
  final String activity;
  final Map<String, dynamic> details;
  final String? notes;
  final OverloadVerdict? verdict;
  final String? reason;
}

@immutable
class WorkoutDay {
  const WorkoutDay({
    required this.date,
    required this.isToday,
    required this.planned,
    required this.logs,
    required this.status,
  });

  final DateTime date;
  final bool isToday;
  final PlannedSession? planned;
  final List<LoggedWorkout> logs;
  final DayStatus status;
}

@immutable
class WorkoutWeek {
  const WorkoutWeek({
    required this.weekStart,
    required this.weekEnd,
    required this.timezone,
    required this.planStatus,
    required this.days,
  });

  final DateTime weekStart;
  final DateTime weekEnd;
  final String timezone;
  final PlanStatus planStatus;
  final List<WorkoutDay> days;

  WorkoutDay? get today {
    for (final day in days) {
      if (day.isToday) return day;
    }
    return null;
  }
}
