import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../routing/routes.dart';
import '../../shared/widgets/bouncy_button.dart';
import '../../theme/app_theme.dart';
import '../../theme/spacing.dart';
import 'voice_capture.dart';
import 'voice_providers.dart';

/// Full-screen M4A voice capture. Stopping creates a Whisper draft but does
/// not send a message; the voice preview owns the explicit send step.
class VoiceOverlay extends ConsumerStatefulWidget {
  const VoiceOverlay({super.key});

  @override
  ConsumerState<VoiceOverlay> createState() => _VoiceOverlayState();
}

class _VoiceOverlayState extends ConsumerState<VoiceOverlay> {
  Timer? _ticker;
  StreamSubscription<double>? _amplitudeSubscription;
  final List<double> _amplitudes = List<double>.generate(27, (_) => 0.08);
  late final VoiceCapture _capture;

  int _elapsedSeconds = 0;
  bool _recording = false;
  bool _transcribing = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    FocusManager.instance.primaryFocus?.unfocus();
    _capture = ref.read(voiceCaptureProvider);
    HapticFeedback.mediumImpact();
    unawaited(_startRecording());
  }

  Future<void> _startRecording() async {
    setState(() {
      _error = null;
      _elapsedSeconds = 0;
    });
    try {
      await _capture.start();
      if (!mounted) {
        await _capture.cancel();
        return;
      }
      _recording = true;
      _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
        if (mounted) setState(() => _elapsedSeconds++);
      });
      _amplitudeSubscription = _capture.amplitudes.listen((amplitude) {
        if (!mounted) return;
        setState(() {
          _amplitudes
            ..removeAt(0)
            ..add(amplitude);
        });
      });
      setState(() {});
    } on VoicePermissionDeniedException {
      if (mounted) {
        setState(() => _error = 'Microphone access is required to record a voice dump.');
      }
    } on Exception {
      if (mounted) {
        setState(() => _error = 'Couldn’t start recording. Please try again.');
      }
    }
  }

  Future<void> _stopAndPreview() async {
    if (!_recording || _transcribing) return;
    HapticFeedback.mediumImpact();
    _ticker?.cancel();
    setState(() {
      _recording = false;
      _transcribing = true;
      _error = null;
    });

    String? audioPath;
    try {
      final stopFuture = _capture.stop();
      unawaited(_amplitudeSubscription?.cancel());
      audioPath = await stopFuture;
      final draft = await ref
          .read(voiceServiceProvider)
          .transcribe(
            audioPath: audioPath,
            duration: Duration(seconds: _elapsedSeconds),
          );
      if (!mounted) return;
      context.pushReplacement(
        Routes.voicePreview,
        extra: draft,
      );
    } on Exception {
      if (audioPath != null) {
        unawaited(_deleteTemporaryAudio(audioPath));
      }
      if (mounted) {
        setState(() {
          _transcribing = false;
          _error = 'We couldn’t transcribe that recording. Try again.';
        });
      }
    }
  }

  Future<void> _cancel() async {
    _ticker?.cancel();
    await _amplitudeSubscription?.cancel();
    if (_recording) {
      _recording = false;
      await _capture.cancel();
    }
    if (mounted) context.pop();
  }

  @override
  void dispose() {
    _ticker?.cancel();
    unawaited(_amplitudeSubscription?.cancel());
    if (_recording) unawaited(_capture.cancel());
    super.dispose();
  }

  String get _elapsed {
    final m = _elapsedSeconds ~/ 60;
    final s = (_elapsedSeconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final textTheme = theme.textTheme;

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(Spacing.lg),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  IconButton(
                    onPressed: _transcribing ? null : _cancel,
                    icon: Icon(Icons.close, color: theme.colorScheme.onSurface),
                  ),
                  _RecordingBadge(
                    label: _transcribing
                        ? 'Transcribing'
                        : _recording
                        ? 'Recording'
                        : 'Ready',
                    active: _recording,
                  ),
                  const SizedBox(width: 48),
                ],
              ),
            ),
            const Spacer(),
            if (_transcribing)
              const SizedBox(
                width: 54,
                height: 54,
                child: CircularProgressIndicator(strokeWidth: 3),
              )
            else
              _LiveWaveform(amplitudes: _amplitudes),
            const SizedBox(height: Spacing.xl),
            Text(_elapsed, style: textTheme.displaySmall),
            const SizedBox(height: Spacing.xs),
            Text(
              _transcribing
                  ? 'Turning your recording into text…'
                  : 'Say everything. Claw sorts it out.',
              style: textTheme.bodySmall,
            ),
            if (_error != null) ...[
              const SizedBox(height: Spacing.lg),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: Spacing.xl),
                child: Text(
                  _error!,
                  textAlign: TextAlign.center,
                  style: textTheme.bodyMedium?.copyWith(color: theme.colorScheme.error),
                ),
              ),
              const SizedBox(height: Spacing.md),
              if (awaitingPermission)
                const TextButton(
                  onPressed: openAppSettings,
                  child: Text('Open Settings'),
                )
              else
                TextButton(
                  onPressed: _startRecording,
                  child: const Text('Try again'),
                ),
            ],
            const Spacer(),
            Padding(
              padding: const EdgeInsets.all(Spacing.xl),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _CircleButton(
                    icon: Icons.close,
                    label: 'Cancel',
                    color: theme.colorScheme.surfaceContainerHighest,
                    iconColor: theme.colorScheme.onSurface,
                    onTap: _transcribing ? null : _cancel,
                  ),
                  _CircleButton(
                    icon: Icons.stop_rounded,
                    label: _transcribing ? 'Working' : 'Stop',
                    color: _recording
                        ? theme.colorScheme.primary
                        : theme.colorScheme.surfaceContainerHighest,
                    iconColor: _recording
                        ? theme.colorScheme.onPrimary
                        : theme.colorScheme.onSurfaceVariant,
                    size: 76,
                    onTap: _recording ? _stopAndPreview : null,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  bool get awaitingPermission => _error?.startsWith('Microphone access') ?? false;

  Future<void> _deleteTemporaryAudio(String path) async {
    try {
      await File(path).delete();
    } on FileSystemException {
      // Temporary recordings are also reclaimed by the operating system.
    }
  }
}

class _RecordingBadge extends StatefulWidget {
  const _RecordingBadge({required this.label, required this.active});

  final String label;
  final bool active;

  @override
  State<_RecordingBadge> createState() => _RecordingBadgeState();
}

class _RecordingBadgeState extends State<_RecordingBadge> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Spacing.md, vertical: Spacing.xs),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          FadeTransition(
            opacity: widget.active
                ? Tween<double>(begin: 0.3, end: 1).animate(_controller)
                : const AlwaysStoppedAnimation(1),
            child: Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: widget.active ? theme.colorScheme.error : theme.colorScheme.onSurfaceVariant,
                shape: BoxShape.circle,
              ),
            ),
          ),
          const SizedBox(width: Spacing.sm),
          Text(widget.label, style: theme.textTheme.labelLarge),
        ],
      ),
    );
  }
}

class _LiveWaveform extends StatelessWidget {
  const _LiveWaveform({required this.amplitudes});

  final List<double> amplitudes;

  @override
  Widget build(BuildContext context) {
    final accent = Theme.of(context).colorScheme.primary;
    return SizedBox(
      height: 64,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          for (var i = 0; i < amplitudes.length; i++) ...[
            if (i > 0) const SizedBox(width: 4),
            AnimatedContainer(
              duration: const Duration(milliseconds: 80),
              width: 4,
              height: 6 + amplitudes[i] * 54,
              decoration: BoxDecoration(
                color: accent.withValues(alpha: 0.35 + amplitudes[i] * 0.65),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _CircleButton extends StatelessWidget {
  const _CircleButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.iconColor,
    required this.onTap,
    this.size = 64,
  });

  final IconData icon;
  final String label;
  final Color color;
  final Color iconColor;
  final VoidCallback? onTap;
  final double size;

  @override
  Widget build(BuildContext context) {
    return BouncyButton(
      onTap: onTap,
      pressedScale: 0.92,
      child: Opacity(
        opacity: onTap == null ? 0.55 : 1,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: size,
              height: size,
              decoration: BoxDecoration(
                color: color,
                shape: BoxShape.circle,
                boxShadow: AppTheme.softShadow(context),
              ),
              child: Icon(icon, color: iconColor, size: 28),
            ),
            const SizedBox(height: Spacing.sm),
            Text(label, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
