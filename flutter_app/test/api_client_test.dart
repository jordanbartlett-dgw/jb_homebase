import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:jb_homebase_app/shared/api/api_client.dart';

void main() {
  group('sendMessage', () {
    test('posts bearer auth + agent slug + idempotency key, parses reply',
        () async {
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
            (jsonDecode(request.body) as Map<String, dynamic>)['idempotency_key']
                as String,
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
  });
}
