import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:jb_homebase_app/data/repositories/workout_week_repository.dart';
import 'package:jb_homebase_app/shared/api/api_client.dart';
import 'package:jb_homebase_app/shared/api/workout_api_models.dart';
import 'package:jb_homebase_app/shared/models/workout_week.dart';

void main() {
  test('WorkoutWeekPayload parses the endpoint JSON shape', () {
    final payload = WorkoutWeekPayload.fromJson({
      'week_start': '2026-08-03',
      'week_end': '2026-08-09',
      'timezone': 'America/Chicago',
      'plan_status': 'active',
      'days': [
        {
          'date': '2026-08-03',
          'is_today': false,
          'planned': {
            'session_type': 'run',
            'description': 'easy run',
            'targets': {'distance_mi': 3},
          },
          'logs': [
            {
              'id': 'log-1',
              'activity': 'run',
              'details': {'distance_mi': 3.5},
              'notes': 'felt good',
              'verdict': 'positive',
              'reason': '+0.5 mi at same pace vs Jul 27',
            }
          ],
          'day_status': 'logged',
        },
        {
          'date': '2026-08-04',
          'is_today': true,
          'planned': null,
          'logs': <Object>[],
          'day_status': 'empty',
        },
      ],
    });

    expect(payload.planStatus, 'active');
    expect(payload.days, hasLength(2));
    expect(payload.days.first.planned!.sessionType, 'run');
    expect(payload.days.first.logs.single.verdict, 'positive');
    expect(payload.days[1].planned, isNull);
  });

  test('repository maps workout week payload into domain models', () async {
    final apiClient = ApiClient(
      baseUrl: 'https://gateway.test',
      appToken: 'token',
      inner: MockClient((request) async {
        return http.Response(
          jsonEncode({
            'week_start': '2026-08-03',
            'week_end': '2026-08-09',
            'timezone': 'America/Chicago',
            'plan_status': 'active',
            'days': [
              {
                'date': '2026-08-03',
                'is_today': false,
                'planned': {
                  'session_type': 'run',
                  'description': 'easy run',
                  'targets': {'distance_mi': 3},
                },
                'logs': [
                  {
                    'id': 'log-1',
                    'activity': 'run',
                    'details': {'distance_mi': 3.5},
                    'notes': 'felt good',
                    'verdict': 'positive',
                    'reason': '+0.5 mi at same pace vs Jul 27',
                  }
                ],
                'day_status': 'logged',
              },
              {
                'date': '2026-08-04',
                'is_today': true,
                'planned': null,
                'logs': <Object>[],
                'day_status': 'empty',
              },
            ],
          }),
          200,
        );
      }),
    );
    final repository = WorkoutWeekRepository(apiClient);

    final week = await repository.fetchWeek();

    expect(week.planStatus, PlanStatus.active);
    expect(week.days, hasLength(2));
    expect(week.days.first.planned?.sessionType, 'run');
    expect(week.days.first.status, DayStatus.logged);
    expect(week.days.first.logs.single.verdict, OverloadVerdict.positive);
    expect(week.days[1].planned, isNull);
    expect(week.days[1].status, DayStatus.empty);
    expect(week.today, week.days[1]);
  });

  test('repository falls back safely on unknown enum strings', () async {
    final apiClient = ApiClient(
      baseUrl: 'https://gateway.test',
      appToken: 'token',
      inner: MockClient((request) async {
        return http.Response(
          jsonEncode({
            'week_start': '2026-08-03',
            'week_end': '2026-08-09',
            'timezone': 'America/Chicago',
            'plan_status': 'something_new',
            'days': [
              {
                'date': '2026-08-03',
                'is_today': false,
                'planned': null,
                'logs': [
                  {
                    'id': 'log-1',
                    'activity': 'run',
                    'details': <String, dynamic>{},
                    'notes': null,
                    'verdict': 'something_new',
                    'reason': null,
                  }
                ],
                'day_status': 'something_new',
              },
            ],
          }),
          200,
        );
      }),
    );

    final week = await WorkoutWeekRepository(apiClient).fetchWeek();

    expect(week.planStatus, PlanStatus.none);
    expect(week.days.single.status, DayStatus.empty);
    expect(week.days.single.logs.single.verdict, isNull);
  });
}
