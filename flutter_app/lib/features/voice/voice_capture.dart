import 'dart:async';

import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

abstract interface class VoiceCapture {
  Stream<double> get amplitudes;

  Future<void> start();

  Future<String> stop();

  Future<void> cancel();

  Future<void> dispose();
}

class VoicePermissionDeniedException implements Exception {
  const VoicePermissionDeniedException();
}

class NativeVoiceCapture implements VoiceCapture {
  NativeVoiceCapture({AudioRecorder? recorder}) : _recorder = recorder ?? AudioRecorder();

  final AudioRecorder _recorder;

  @override
  Stream<double> get amplitudes =>
      _recorder.onAmplitudeChanged(const Duration(milliseconds: 90)).map((sample) {
        // record reports dBFS (typically -60 silence → 0 peak). Keep a small
        // floor so the waveform remains legible in a quiet room.
        return ((sample.current + 60) / 60).clamp(0.06, 1.0);
      });

  @override
  Future<void> start() async {
    final permission = await Permission.microphone.request();
    if (!permission.isGranted) throw const VoicePermissionDeniedException();

    final directory = await getTemporaryDirectory();
    final path = '${directory.path}/voice-${DateTime.now().microsecondsSinceEpoch}.m4a';
    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.aacLc,
        bitRate: 128000,
        sampleRate: 44100,
        numChannels: 1,
      ),
      path: path,
    );
  }

  @override
  Future<String> stop() async {
    final path = await _recorder.stop();
    if (path == null || path.isEmpty) {
      throw StateError('Recorder did not return an audio file.');
    }
    return path;
  }

  @override
  Future<void> cancel() => _recorder.cancel();

  @override
  Future<void> dispose() => _recorder.dispose();
}
