class VoiceDraft {
  const VoiceDraft({
    required this.audioPath,
    required this.transcript,
    required this.idempotencyKey,
    required this.duration,
  });

  final String audioPath;
  final String transcript;
  final String idempotencyKey;
  final Duration duration;
}
