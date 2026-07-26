import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:jb_homebase_app/shared/api/api_client.dart';

Map<String, dynamic> conversationJson({
  String id = 'c1',
  String status = 'active',
}) {
  return {
    'conversation': {
      'id': id,
      'agent_slug': 'claw-main',
      'status': status,
      'title': 'Plan my day',
      'message_count': 2,
      'created_at': '2026-07-24T14:00:00Z',
      'last_message_at': '2026-07-24T14:01:00Z',
    },
    'messages': [
      {
        'id': 'm1',
        'role': 'user',
        'content': 'Plan my day',
        'created_at': '2026-07-24T14:00:00Z',
      },
      {
        'id': 'm2',
        'role': 'assistant',
        'content': 'Here is the plan.',
        'created_at': '2026-07-24T14:01:00Z',
      },
    ],
  };
}

void main() {
  group('sendMessage', () {
    test('posts bearer auth + agent slug + idempotency key, parses reply', () async {
      late http.Request captured;
      final client = ApiClient(
        baseUrl: 'https://gateway.test',
        appToken: 'claw-token',
        inner: MockClient((request) async {
          captured = request;
          return http.Response(
            jsonEncode({
              'agent_slug': 'workout-coach',
              'reply': 'Logged it.',
              'conversation_id': 'c1',
            }),
            200,
            headers: {'content-type': 'application/json'},
          );
        }),
      );

      final reply = await client.sendMessage(
        agentSlug: 'workout-coach',
        text: 'log my workout',
      );

      expect(captured.url.toString(), 'https://gateway.test/app/messages');
      expect(captured.headers['Authorization'], 'Bearer claw-token');
      final body = jsonDecode(captured.body) as Map<String, dynamic>;
      expect(body['text'], 'log my workout');
      expect(body['agent_slug'], 'workout-coach');
      expect(body['idempotency_key'], isNotEmpty);
      expect(reply.agentSlug, 'workout-coach');
      expect(reply.reply, 'Logged it.');
      expect(reply.conversationId, 'c1');
    });

    test('consecutive sends carry distinct idempotency keys', () async {
      final keys = <String>[];
      final client = ApiClient(
        baseUrl: 'https://gateway.test',
        appToken: 'claw-token',
        inner: MockClient((request) async {
          keys.add(
            (jsonDecode(request.body) as Map<String, dynamic>)['idempotency_key'] as String,
          );
          return http.Response(
            jsonEncode({'agent_slug': 'claw-main', 'reply': 'ok'}),
            200,
          );
        }),
      );

      await client.sendMessage(agentSlug: 'claw-main', text: 'one');
      await client.sendMessage(agentSlug: 'claw-main', text: 'two');

      expect(keys, hasLength(2));
      expect(keys[0], isNot(keys[1]));
    });

    test('throws ApiException with status on auth failure', () async {
      final client = ApiClient(
        baseUrl: 'https://gateway.test',
        appToken: 'wrong-token',
        inner: MockClient((request) async => http.Response('', 401)),
      );

      expect(
        () => client.sendMessage(agentSlug: 'claw-main', text: 'hi'),
        throwsA(
          isA<ApiException>().having((e) => e.statusCode, 'statusCode', 401),
        ),
      );
    });
  });

  group('sendVoice', () {
    test('posts raw bytes with audio headers, parses transcript', () async {
      late http.Request captured;
      final client = ApiClient(
        baseUrl: 'https://gateway.test',
        appToken: 'claw-token',
        inner: MockClient((request) async {
          captured = request;
          return http.Response(
            jsonEncode({
              'transcript': 'log my workout',
              'agent_slug': 'workout-coach',
              'reply': 'Logged it.',
            }),
            200,
          );
        }),
      );

      final reply = await client.sendVoice(
        audioBytes: [0, 1, 2, 3],
        filename: 'note.m4a',
      );

      expect(captured.url.toString(), 'https://gateway.test/voice');
      expect(captured.headers['Authorization'], 'Bearer claw-token');
      expect(captured.headers['X-Audio-Filename'], 'note.m4a');
      expect(captured.headers['X-Idempotency-Key'], isNotEmpty);
      expect(captured.bodyBytes, [0, 1, 2, 3]);
      expect(reply.transcript, 'log my workout');
      expect(reply.agentSlug, 'workout-coach');
      expect(reply.reply, 'Logged it.');
    });

    test('transcribes a draft without sending it', () async {
      late http.Request captured;
      final client = ApiClient(
        baseUrl: 'https://gateway.test',
        appToken: 'claw-token',
        inner: MockClient((request) async {
          captured = request;
          return http.Response(
            jsonEncode({'transcript': 'review this first'}),
            200,
          );
        }),
      );

      final transcript = await client.transcribeVoice(
        audioBytes: [4, 5, 6],
        filename: 'draft.m4a',
        idempotencyKey: 'draft-123',
      );

      expect(captured.url.toString(), 'https://gateway.test/voice/transcribe');
      expect(captured.headers['Authorization'], 'Bearer claw-token');
      expect(captured.headers['X-Audio-Filename'], 'draft.m4a');
      expect(captured.headers['X-Idempotency-Key'], 'draft-123');
      expect(captured.bodyBytes, [4, 5, 6]);
      expect(transcript, 'review this first');
    });

    test('sends the edited transcript with the draft idempotency key', () async {
      late http.Request captured;
      final client = ApiClient(
        baseUrl: 'https://gateway.test',
        appToken: 'claw-token',
        inner: MockClient((request) async {
          captured = request;
          return http.Response(
            jsonEncode({
              'transcript': 'edited workout',
              'agent_slug': 'workout-coach',
              'reply': 'Logged it.',
            }),
            200,
          );
        }),
      );

      final reply = await client.sendVoiceTranscript(
        transcript: 'edited workout',
        idempotencyKey: 'draft-123',
      );

      expect(captured.url.toString(), 'https://gateway.test/voice/messages');
      expect(captured.headers['Authorization'], 'Bearer claw-token');
      final body = jsonDecode(captured.body) as Map<String, dynamic>;
      expect(body['transcript'], 'edited workout');
      expect(body['idempotency_key'], 'draft-123');
      expect(reply.agentSlug, 'workout-coach');
      expect(reply.reply, 'Logged it.');
    });
  });

  group('conversation history', () {
    test('lists a cursor page with bearer auth', () async {
      late http.Request captured;
      final detail = conversationJson();
      final client = ApiClient(
        baseUrl: 'https://gateway.test',
        appToken: 'claw-token',
        inner: MockClient((request) async {
          captured = request;
          return http.Response(
            jsonEncode({
              'conversations': [detail['conversation']],
              'next_before': '2026-07-20T00:00:00Z',
            }),
            200,
          );
        }),
      );

      final page = await client.listConversations(
        before: '2026-07-25T00:00:00Z',
      );

      expect(captured.method, 'GET');
      expect(captured.headers['Authorization'], 'Bearer claw-token');
      expect(captured.url.path, '/app/conversations');
      expect(captured.url.queryParameters['limit'], '20');
      expect(
        captured.url.queryParameters['before'],
        '2026-07-25T00:00:00Z',
      );
      expect(page.conversations.single.title, 'Plan my day');
      expect(page.nextBefore, '2026-07-20T00:00:00Z');
    });

    test('hydrates the current conversation and handles no active chat', () async {
      var returnNull = false;
      final client = ApiClient(
        baseUrl: 'https://gateway.test',
        appToken: 'claw-token',
        inner: MockClient((request) async {
          expect(
            request.url.queryParameters['agent_slug'],
            'claw-main',
          );
          return http.Response(
            returnNull ? 'null' : jsonEncode(conversationJson()),
            200,
          );
        }),
      );

      final current = await client.currentConversation('claw-main');
      expect(current?.messages.last.content, 'Here is the plan.');

      returnNull = true;
      expect(await client.currentConversation('claw-main'), isNull);
    });

    test('loads a transcript and starts a new chat', () async {
      final requests = <http.Request>[];
      final client = ApiClient(
        baseUrl: 'https://gateway.test',
        appToken: 'claw-token',
        inner: MockClient((request) async {
          requests.add(request);
          if (request.method == 'POST') {
            return http.Response(
              jsonEncode({'archived_conversation_id': 'c1'}),
              200,
            );
          }
          return http.Response(jsonEncode(conversationJson()), 200);
        }),
      );

      final detail = await client.conversation('c1');
      await client.startNewConversation('claw-main');

      expect(detail.messages, hasLength(2));
      expect(requests.first.url.path, '/app/conversations/c1');
      expect(requests.last.url.path, '/app/conversations/new');
      expect(
        jsonDecode(requests.last.body)['agent_slug'],
        'claw-main',
      );
    });
  });

  group('today', () {
    test('fetches bearer-authenticated digest and calendar payload', () async {
      late http.Request captured;
      final client = ApiClient(
        baseUrl: 'https://gateway.test',
        appToken: 'claw-token',
        inner: MockClient((request) async {
          captured = request;
          return http.Response(
            jsonEncode({
              'date': '2026-07-25',
              'timezone': 'America/Chicago',
              'digest': {
                'id': 'digest-1',
                'content': 'Your briefing is ready.',
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

      final today = await client.fetchToday();

      expect(captured.method, 'GET');
      expect(captured.url.path, '/app/today');
      expect(captured.url.queryParameters['days'], '7');
      expect(captured.headers['Authorization'], 'Bearer claw-token');
      expect(today.digest?.content, 'Your briefing is ready.');
      expect(today.events.single.title, 'Board call');
      expect(today.events.single.location, 'Zoom');
    });
  });
}
