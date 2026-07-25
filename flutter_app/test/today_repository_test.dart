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
  });
}
