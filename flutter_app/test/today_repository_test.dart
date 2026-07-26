import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:jb_homebase_app/data/repositories/today_repository.dart';
import 'package:jb_homebase_app/shared/api/api_client.dart';

void main() {
  test('repository maps Today payload into domain models', () async {
    final apiClient = ApiClient(
      baseUrl: 'https://gateway.test',
      appToken: 'token',
      inner: MockClient((request) async {
        return http.Response(
          jsonEncode({
            'date': '2026-07-25',
            'timezone': 'America/Chicago',
            'digest': {
              'id': 'digest-1',
              'content': 'Review the board agenda.',
              'generated_at': '2026-07-25T07:02:00-05:00',
            },
            'calendar_status': 'ok',
            'calendar_message': null,
            'events': [
              {
                'id': 'event-1',
                'title': 'Board call',
                'starts_at': '2026-07-25T10:00:00-05:00',
                'ends_at': '2026-07-25T11:00:00-05:00',
                'all_day': false,
                'location': 'Zoom',
              },
            ],
            'artifacts': [
              {
                'task_type': 'memory_flag',
                'content': 'I updated my understanding.',
                'created_at': '2026-07-25T08:04:00-05:00',
              },
              {
                'task_type': 'event_trigger',
                'content': 'A new message reached the agent inbox.',
                'created_at': '2026-07-25T07:48:00-05:00',
              },
            ],
          }),
          200,
        );
      }),
    );
    final repository = TodayRepository(apiClient);

    final today = await repository.fetchToday();

    expect(today.digest?.content, 'Review the board agenda.');
    expect(today.calendarAvailable, isTrue);
    expect(today.events.single.title, 'Board call');
    expect(today.events.single.allDay, isFalse);
    expect(today.events.single.location, 'Zoom');
    expect(today.artifacts, hasLength(2));
    expect(today.artifacts.first.taskType, 'memory_flag');
    expect(today.artifacts.first.content, 'I updated my understanding.');
    expect(today.artifacts.last.taskType, 'event_trigger');
  });

  test('repository accepts older Today payloads without artifacts', () async {
    final apiClient = ApiClient(
      baseUrl: 'https://gateway.test',
      appToken: 'token',
      inner: MockClient((request) async {
        return http.Response(
          jsonEncode({
            'date': '2026-07-25',
            'timezone': 'America/Chicago',
            'digest': null,
            'calendar_status': 'ok',
            'calendar_message': null,
            'events': <Object>[],
          }),
          200,
        );
      }),
    );

    final today = await TodayRepository(apiClient).fetchToday();

    expect(today.artifacts, isEmpty);
  });
}
