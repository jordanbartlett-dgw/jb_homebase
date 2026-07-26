import '../../shared/api/api_client.dart';
import '../../shared/models/today.dart';

class TodayRepository {
  const TodayRepository(this._apiClient);

  final ApiClient _apiClient;

  Future<TodayOverview> fetchToday() async {
    final payload = await _apiClient.fetchToday();
    final digest = payload.digest;
    return TodayOverview(
      date: payload.date,
      timezone: payload.timezone,
      digest: digest == null
          ? null
          : DailyDigest(
              id: digest.id,
              content: digest.content,
              generatedAt: digest.generatedAt,
            ),
      calendarAvailable: payload.calendarStatus == 'ok',
      calendarMessage: payload.calendarMessage,
      events: [
        for (final event in payload.events)
          CalendarEvent(
            id: event.id,
            title: event.title,
            startsAt: event.startsAt,
            endsAt: event.endsAt,
            allDay: event.allDay,
            location: event.location,
          ),
      ],
      artifacts: [
        for (final artifact in payload.artifacts)
          ProactiveArtifact(
            taskType: artifact.taskType,
            content: artifact.content,
            createdAt: artifact.createdAt,
          ),
      ],
    );
  }
}
