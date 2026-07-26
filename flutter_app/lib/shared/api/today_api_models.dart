class DailyDigestPayload {
  const DailyDigestPayload({
    required this.id,
    required this.content,
    required this.generatedAt,
  });

  factory DailyDigestPayload.fromJson(Map<String, dynamic> json) {
    return DailyDigestPayload(
      id: json['id'] as String,
      content: json['content'] as String,
      generatedAt: DateTime.parse(json['generated_at'] as String),
    );
  }

  final String id;
  final String content;
  final DateTime generatedAt;
}

class CalendarEventPayload {
  const CalendarEventPayload({
    required this.id,
    required this.title,
    required this.startsAt,
    required this.endsAt,
    required this.allDay,
    required this.location,
  });

  factory CalendarEventPayload.fromJson(Map<String, dynamic> json) {
    return CalendarEventPayload(
      id: json['id'] as String,
      title: json['title'] as String,
      startsAt: DateTime.parse(json['starts_at'] as String),
      endsAt: DateTime.parse(json['ends_at'] as String),
      allDay: json['all_day'] as bool,
      location: json['location'] as String?,
    );
  }

  final String id;
  final String title;
  final DateTime startsAt;
  final DateTime endsAt;
  final bool allDay;
  final String? location;
}

class ProactiveArtifactPayload {
  const ProactiveArtifactPayload({
    required this.taskType,
    required this.content,
    required this.createdAt,
  });

  factory ProactiveArtifactPayload.fromJson(Map<String, dynamic> json) {
    return ProactiveArtifactPayload(
      taskType: json['task_type'] as String,
      content: json['content'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  final String taskType;
  final String content;
  final DateTime createdAt;
}

class TodayPayload {
  const TodayPayload({
    required this.date,
    required this.timezone,
    required this.digest,
    required this.calendarStatus,
    required this.calendarMessage,
    required this.events,
    required this.artifacts,
  });

  factory TodayPayload.fromJson(Map<String, dynamic> json) {
    final digestJson = json['digest'] as Map<String, dynamic>?;
    return TodayPayload(
      date: DateTime.parse(json['date'] as String),
      timezone: json['timezone'] as String,
      digest: digestJson == null ? null : DailyDigestPayload.fromJson(digestJson),
      calendarStatus: json['calendar_status'] as String,
      calendarMessage: json['calendar_message'] as String?,
      events: [
        for (final event in json['events'] as List<dynamic>)
          CalendarEventPayload.fromJson(event as Map<String, dynamic>),
      ],
      artifacts: [
        for (final artifact in json['artifacts'] as List<dynamic>? ?? const [])
          ProactiveArtifactPayload.fromJson(
            artifact as Map<String, dynamic>,
          ),
      ],
    );
  }

  final DateTime date;
  final String timezone;
  final DailyDigestPayload? digest;
  final String calendarStatus;
  final String? calendarMessage;
  final List<CalendarEventPayload> events;
  final List<ProactiveArtifactPayload> artifacts;
}
