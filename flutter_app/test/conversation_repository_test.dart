import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:jb_homebase_app/data/repositories/conversation_repository.dart';
import 'package:jb_homebase_app/shared/api/api_client.dart';
import 'package:jb_homebase_app/shared/models/message.dart';

Map<String, dynamic> _summary() {
  return {
    'id': 'c1',
    'agent_slug': 'claw-main',
    'status': 'active',
    'title': 'Plan my day',
    'message_count': 2,
    'created_at': '2026-07-24T14:00:00Z',
    'last_message_at': '2026-07-24T14:01:00Z',
  };
}

void main() {
  test('repository maps wire history and transcript into domain models', () async {
    final apiClient = ApiClient(
      baseUrl: 'https://gateway.test',
      appToken: 'token',
      inner: MockClient((request) async {
        if (request.url.path.endsWith('/current')) {
          return http.Response(
            jsonEncode({
              'conversation': _summary(),
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
            }),
            200,
          );
        }
        return http.Response(
          jsonEncode({
            'conversations': [_summary()],
            'next_before': null,
          }),
          200,
        );
      }),
    );
    final repository = ConversationRepository(apiClient);

    final page = await repository.listConversations();
    final current = await repository.currentConversation('claw-main');

    expect(page.conversations.single.title, 'Plan my day');
    expect(page.nextBefore, isNull);
    expect(current?.messages.first.role, MessageRole.user);
    expect(current?.messages.last.role, MessageRole.assistant);
    expect(current?.messages.last.body, 'Here is the plan.');
  });
}
