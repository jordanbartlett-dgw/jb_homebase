import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../state/core_providers.dart';
import 'voice_capture.dart';
import 'voice_service.dart';

final voiceCaptureProvider = Provider<VoiceCapture>((ref) {
  final capture = NativeVoiceCapture();
  ref.onDispose(capture.dispose);
  return capture;
});

final voiceServiceProvider = Provider<VoiceService>((ref) {
  return buildVoiceService(ref.watch(apiClientProvider));
});
