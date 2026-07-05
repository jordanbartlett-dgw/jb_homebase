import 'dart:convert';

import 'package:http/http.dart' as http;

import 'gateway_config.dart';

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
/// Blocking request/reply (no streaming): agent runs take 30-60s and the
/// gateway converges Railway edge replays server-side via the idempotency
/// key, so a generous client timeout is safe. The typing indicator covers
/// the wait.
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
  String _idempotencyKey() =>
      '${DateTime.now().microsecondsSinceEpoch}-${_keySeq++}';

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
            'idempotency_key': _idempotencyKey(),
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
            'X-Idempotency-Key': _idempotencyKey(),
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
