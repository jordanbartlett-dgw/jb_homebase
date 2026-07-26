import 'dart:convert';

import 'package:http/http.dart' as http;

import 'conversation_api_models.dart';
import 'gateway_config.dart';
import 'message_stream_event.dart';
import 'today_api_models.dart';

/// Reply from the gateway for one sent message (text or voice).
class AgentReply {
  const AgentReply({
    required this.agentSlug,
    required this.reply,
    this.conversationId,
    this.transcript,
  });

  final String agentSlug;
  final String reply;
  final String? conversationId;

  /// Whisper transcript — only present on voice sends.
  final String? transcript;
}

class ApiException implements Exception {
  const ApiException(this.statusCode, this.message);

  final int statusCode;
  final String message;

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// HTTP client for the Jordan Claw gateway.
///
/// Text chat streams safe progress and answer deltas. Voice and the legacy
/// text method remain blocking. Every message carries a stable idempotency key
/// so a retry converges on the original gateway run.
class ApiClient {
  ApiClient({
    http.Client? inner,
    this.baseUrl = GatewayConfig.baseUrl,
    this.appToken = GatewayConfig.appToken,
  }) : _inner = inner ?? http.Client();

  final http.Client _inner;
  final String baseUrl;
  final String appToken;

  static const _timeout = Duration(seconds: 120);

  static int _keySeq = 0;

  /// One key per utterance; a Railway edge replay of the same request
  /// carries the same key and converges on the original reply.
  String createIdempotencyKey() => '${DateTime.now().microsecondsSinceEpoch}-${_keySeq++}';

  /// POST /app/messages — text chat with an explicit agent.
  Future<AgentReply> sendMessage({
    required String agentSlug,
    required String text,
  }) async {
    final resp = await _inner
        .post(
          Uri.parse('$baseUrl/app/messages'),
          headers: {
            'Authorization': 'Bearer $appToken',
            'Content-Type': 'application/json',
          },
          body: jsonEncode({
            'text': text,
            'agent_slug': agentSlug,
            'idempotency_key': createIdempotencyKey(),
          }),
        )
        .timeout(_timeout);
    final body = _decode(resp);
    return AgentReply(
      agentSlug: body['agent_slug'] as String,
      reply: body['reply'] as String,
      conversationId: body['conversation_id'] as String?,
    );
  }

  /// POST /app/messages/stream — safe activity, final-text deltas, completion.
  ///
  /// A dropped transport gets one automatic reconnect with the same key. The
  /// gateway may only return status + completion on a reconnect because the
  /// original agent stream is allowed to finish independently.
  Stream<MessageStreamEvent> sendMessageStream({
    required String agentSlug,
    required String text,
  }) async* {
    final idempotencyKey = createIdempotencyKey();
    Object? lastError;

    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        await for (final event in _messageStreamAttempt(
          agentSlug: agentSlug,
          text: text,
          idempotencyKey: idempotencyKey,
        )) {
          yield event;
          if (event.type == MessageStreamEventType.complete ||
              event.type == MessageStreamEventType.error) {
            return;
          }
        }
        throw const ApiException(0, 'Message stream ended before completion');
      } on Exception catch (error) {
        lastError = error;
        if (attempt == 1) rethrow;
      }
    }

    throw lastError ?? const ApiException(0, 'Message stream failed');
  }

  Stream<MessageStreamEvent> _messageStreamAttempt({
    required String agentSlug,
    required String text,
    required String idempotencyKey,
  }) async* {
    final request =
        http.Request(
            'POST',
            Uri.parse('$baseUrl/app/messages/stream'),
          )
          ..headers.addAll({
            'Authorization': 'Bearer $appToken',
            'Content-Type': 'application/json',
            'Accept': 'application/x-ndjson',
          })
          ..body = jsonEncode({
            'text': text,
            'agent_slug': agentSlug,
            'idempotency_key': idempotencyKey,
          });

    final response = await _inner.send(request).timeout(_timeout);
    if (response.statusCode != 200) {
      final body = await response.stream.bytesToString();
      throw ApiException(
        response.statusCode,
        body.isEmpty ? 'HTTP ${response.statusCode}' : body,
      );
    }

    final lines = response.stream
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .timeout(_timeout);
    await for (final line in lines) {
      if (line.trim().isEmpty) continue;
      final json = jsonDecode(line) as Map<String, dynamic>;
      yield MessageStreamEvent.fromJson(json);
    }
  }

  /// POST /voice — raw audio bytes; the gateway transcribes, routes to an
  /// agent via its classifier, and returns transcript + reply.
  Future<AgentReply> sendVoice({
    required List<int> audioBytes,
    String filename = 'voice.m4a',
    String contentType = 'audio/m4a',
  }) async {
    final resp = await _inner
        .post(
          Uri.parse('$baseUrl/voice'),
          headers: {
            'Authorization': 'Bearer $appToken',
            'Content-Type': contentType,
            'X-Audio-Filename': filename,
            'X-Idempotency-Key': createIdempotencyKey(),
          },
          body: audioBytes,
        )
        .timeout(_timeout);
    final body = _decode(resp);
    return AgentReply(
      agentSlug: body['agent_slug'] as String,
      reply: body['reply'] as String,
      transcript: body['transcript'] as String?,
    );
  }

  /// POST /voice/transcribe — create a server-side Whisper draft without
  /// creating a conversation message or running an agent.
  Future<String> transcribeVoice({
    required List<int> audioBytes,
    required String idempotencyKey,
    String filename = 'voice.m4a',
    String contentType = 'audio/m4a',
  }) async {
    final resp = await _inner
        .post(
          Uri.parse('$baseUrl/voice/transcribe'),
          headers: {
            'Authorization': 'Bearer $appToken',
            'Content-Type': contentType,
            'X-Audio-Filename': filename,
            'X-Idempotency-Key': idempotencyKey,
          },
          body: audioBytes,
        )
        .timeout(_timeout);
    return _decode(resp)['transcript'] as String;
  }

  /// POST /voice/messages — send the reviewed (and optionally edited)
  /// transcript. The same utterance key is reused for replay convergence.
  Future<AgentReply> sendVoiceTranscript({
    required String transcript,
    required String idempotencyKey,
  }) async {
    final resp = await _inner
        .post(
          Uri.parse('$baseUrl/voice/messages'),
          headers: {
            'Authorization': 'Bearer $appToken',
            'Content-Type': 'application/json',
          },
          body: jsonEncode({
            'transcript': transcript,
            'idempotency_key': idempotencyKey,
          }),
        )
        .timeout(_timeout);
    final body = _decode(resp);
    return AgentReply(
      agentSlug: body['agent_slug'] as String,
      reply: body['reply'] as String,
      transcript: body['transcript'] as String?,
    );
  }

  /// GET /app/conversations — one cursor-paginated history page.
  Future<ConversationPagePayload> listConversations({String? before}) async {
    final query = <String, String>{'limit': '20'};
    if (before != null) query['before'] = before;
    final uri = Uri.parse(
      '$baseUrl/app/conversations',
    ).replace(queryParameters: query);
    final resp = await _inner.get(uri, headers: _authorizationHeaders()).timeout(_timeout);
    return ConversationPagePayload.fromJson(_decode(resp));
  }

  /// GET /app/conversations/current — active transcript for app hydration.
  Future<ConversationDetailPayload?> currentConversation(
    String agentSlug,
  ) async {
    final uri = Uri.parse('$baseUrl/app/conversations/current').replace(
      queryParameters: {'agent_slug': agentSlug},
    );
    final resp = await _inner.get(uri, headers: _authorizationHeaders()).timeout(_timeout);
    final decoded = _decodeNullable(resp);
    return decoded == null ? null : ConversationDetailPayload.fromJson(decoded);
  }

  /// GET /app/conversations/{id} — read-only transcript from History.
  Future<ConversationDetailPayload> conversation(
    String conversationId,
  ) async {
    final encodedId = Uri.encodeComponent(conversationId);
    final resp = await _inner
        .get(
          Uri.parse('$baseUrl/app/conversations/$encodedId'),
          headers: _authorizationHeaders(),
        )
        .timeout(_timeout);
    return ConversationDetailPayload.fromJson(_decode(resp));
  }

  /// POST /app/conversations/new — archive current; next send starts clean.
  Future<void> startNewConversation(String agentSlug) async {
    final resp = await _inner
        .post(
          Uri.parse('$baseUrl/app/conversations/new'),
          headers: {
            ..._authorizationHeaders(),
            'Content-Type': 'application/json',
          },
          body: jsonEncode({'agent_slug': agentSlug}),
        )
        .timeout(_timeout);
    _decode(resp);
  }

  /// GET /app/today — existing briefing plus a seven-day calendar agenda.
  Future<TodayPayload> fetchToday() async {
    final uri = Uri.parse(
      '$baseUrl/app/today',
    ).replace(queryParameters: {'days': '7'});
    final resp = await _inner.get(uri, headers: _authorizationHeaders()).timeout(_timeout);
    return TodayPayload.fromJson(_decode(resp));
  }

  Map<String, String> _authorizationHeaders() {
    return {'Authorization': 'Bearer $appToken'};
  }

  Map<String, dynamic>? _decodeNullable(http.Response resp) {
    if (resp.statusCode != 200) {
      throw ApiException(
        resp.statusCode,
        resp.body.isEmpty ? 'HTTP ${resp.statusCode}' : resp.body,
      );
    }
    final decoded = jsonDecode(resp.body);
    return decoded == null ? null : decoded as Map<String, dynamic>;
  }

  Map<String, dynamic> _decode(http.Response resp) {
    if (resp.statusCode != 200) {
      throw ApiException(
        resp.statusCode,
        resp.body.isEmpty ? 'HTTP ${resp.statusCode}' : resp.body,
      );
    }
    return jsonDecode(resp.body) as Map<String, dynamic>;
  }

  void dispose() {
    _inner.close();
  }
}
