import 'package:flutter/foundation.dart';

@immutable
class DailyDigest {
  const DailyDigest({
    required this.id,
    required this.content,
    required this.generatedAt,
  });

  final String id;
  final String content;
  final DateTime generatedAt;
}

@immutable
class CalendarEvent {
  const CalendarEvent({
    required this.id,
    required this.title,
    required this.startsAt,
    required this.endsAt,
    required this.allDay,
    required this.location,
  });

  final String id;
  final String title;
  final DateTime startsAt;
  final DateTime endsAt;
  final bool allDay;
  final String? location;
}

@immutable
class ProactiveArtifact {
  const ProactiveArtifact({
    required this.taskType,
    required this.content,
    required this.createdAt,
  });

  final String taskType;
  final String content;
  final DateTime createdAt;
}

@immutable
class TodayOverview {
  const TodayOverview({
    required this.date,
    required this.timezone,
    required this.digest,
    required this.calendarAvailable,
    required this.calendarMessage,
    required this.events,
    required this.artifacts,
  });

  final DateTime date;
  final String timezone;
  final DailyDigest? digest;
  final bool calendarAvailable;
  final String? calendarMessage;
  final List<CalendarEvent> events;
  final List<ProactiveArtifact> artifacts;

  List<CalendarEvent> upcomingEvents({DateTime? now}) {
    final current = now ?? DateTime.now();
    return [
      for (final event in events)
        if (event.allDay || event.endsAt.toLocal().isAfter(current)) event,
    ];
  }
}
