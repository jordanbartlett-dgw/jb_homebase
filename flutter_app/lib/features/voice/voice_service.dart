import 'dart:io';

import '../../shared/api/api_client.dart';
import '../../shared/api/gateway_config.dart';
import 'voice_draft.dart';

abstract interface class VoiceService {
  Future<VoiceDraft> transcribe({
    required String audioPath,
    required Duration duration,
  });

  Future<AgentReply> send({
    required VoiceDraft draft,
    required String transcript,
  });
}

class GatewayVoiceService implements VoiceService {
  GatewayVoiceService(this._api);

  final ApiClient _api;

  @override
  Future<VoiceDraft> transcribe({
    required String audioPath,
    required Duration duration,
  }) async {
    final key = _api.createIdempotencyKey();
    final file = File(audioPath);
    final transcript = await _api.transcribeVoice(
      audioBytes: await file.readAsBytes(),
      filename: file.uri.pathSegments.last,
      idempotencyKey: key,
    );
    return VoiceDraft(
      audioPath: audioPath,
      transcript: transcript,
      idempotencyKey: key,
      duration: duration,
    );
  }

  @override
  Future<AgentReply> send({
    required VoiceDraft draft,
    required String transcript,
  }) {
    return _api.sendVoiceTranscript(
      transcript: transcript,
      idempotencyKey: draft.idempotencyKey,
    );
  }
}

class DemoVoiceService implements VoiceService {
  const DemoVoiceService();

  @override
  Future<VoiceDraft> transcribe({
    required String audioPath,
    required Duration duration,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 500));
    return VoiceDraft(
      audioPath: audioPath,
      transcript: 'Review this voice transcript before sending it.',
      idempotencyKey: 'demo-${DateTime.now().microsecondsSinceEpoch}',
      duration: duration,
    );
  }

  @override
  Future<AgentReply> send({
    required VoiceDraft draft,
    required String transcript,
  }) async {
    await Future<void>.delayed(const Duration(milliseconds: 700));
    return AgentReply(
      agentSlug: 'claw-main',
      transcript: transcript,
      reply: 'Got it. (Mock voice reply.)',
    );
  }
}

VoiceService buildVoiceService(ApiClient api) {
  return GatewayConfig.isLive ? GatewayVoiceService(api) : const DemoVoiceService();
}
