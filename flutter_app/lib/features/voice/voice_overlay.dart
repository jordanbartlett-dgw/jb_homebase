import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';

import '../../shared/widgets/bouncy_button.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import 'voice_preview.dart';

/// Full-screen voice capture modal. UI only — no real audio capture in v1
/// scaffold. Real `record` integration lands in PR2; the waveform then
/// renders live amplitude instead of this idle animation.
class VoiceOverlay extends StatefulWidget {
  const VoiceOverlay({super.key});

  @override
  State<VoiceOverlay> createState() => _VoiceOverlayState();
}

class _VoiceOverlayState extends State<VoiceOverlay> {
  Timer? _ticker;
  int _elapsedSeconds = 0;

  @override
  void initState() {
    super.initState();
    HapticFeedback.mediumImpact();
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      setState(() => _elapsedSeconds++);
    });
  }

  @override
  void dispose() {
    _ticker?.cancel();
    super.dispose();
  }

  String get _elapsed {
    final m = _elapsedSeconds ~/ 60;
    final s = (_elapsedSeconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  void _stopAndPreview(BuildContext context) {
    // TODO(backend): stop `record` session, hand the audio file to the preview.
    HapticFeedback.mediumImpact();
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(
        builder: (_) => const VoicePreview(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(Spacing.lg),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  IconButton(
                    onPressed: () => context.pop(),
                    icon: const Icon(Icons.close, color: AppColors.textPrimary),
                  ),
                  const _RecordingBadge(),
                  const SizedBox(width: 48),
                ],
              ),
            ),
            const Spacer(),
            const _LiveWaveform(),
            const SizedBox(height: Spacing.xl),
            Text(_elapsed, style: textTheme.displaySmall),
            const SizedBox(height: Spacing.xs),
            Text('Say everything. Claw sorts it out.',
                style: textTheme.bodySmall),
            const Spacer(),
            Padding(
              padding: const EdgeInsets.all(Spacing.xl),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  _CircleButton(
                    icon: Icons.close,
                    label: 'Cancel',
                    color: AppColors.surfaceVariant,
                    iconColor: AppColors.textPrimary,
                    onTap: () => context.pop(),
                  ),
                  _CircleButton(
                    icon: Icons.stop_rounded,
                    label: 'Stop',
                    color: AppColors.accent,
                    iconColor: AppColors.onAccent,
                    size: 76,
                    onTap: () => _stopAndPreview(context),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "Recording" pill with a pulsing red dot.
class _RecordingBadge extends StatefulWidget {
  const _RecordingBadge();

  @override
  State<_RecordingBadge> createState() => _RecordingBadgeState();
}

class _RecordingBadgeState extends State<_RecordingBadge>
    with SingleTickerProviderStateMixin {
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
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Spacing.md,
        vertical: Spacing.xs,
      ),
      decoration: BoxDecoration(
        color: AppColors.surfaceVariant,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          FadeTransition(
            opacity: Tween<double>(begin: 0.3, end: 1).animate(_controller),
            child: Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                color: AppColors.error,
                shape: BoxShape.circle,
              ),
            ),
          ),
          const SizedBox(width: Spacing.sm),
          Text('Recording', style: Theme.of(context).textTheme.labelLarge),
        ],
      ),
    );
  }
}

/// Idle waveform animation — bars breathe on offset sine waves so the
/// surface feels live. Real amplitude data replaces this in PR2.
class _LiveWaveform extends StatefulWidget {
  const _LiveWaveform();

  @override
  State<_LiveWaveform> createState() => _LiveWaveformState();
}

class _LiveWaveformState extends State<_LiveWaveform>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  static const _barCount = 27;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  double _heightFor(int index, double phase) {
    // Two overlapping sine waves at different frequencies read as speech
    // cadence rather than a metronome.
    final t = phase * 2 * math.pi;
    final a = math.sin(t + index * 0.9);
    final b = math.sin(t * 1.7 + index * 0.35);
    final envelope = math.sin(index / (_barCount - 1) * math.pi);
    final wave = (a + b + 2) / 4;
    return 6 + envelope * wave * 52;
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 64,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          return Row(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              for (var i = 0; i < _barCount; i++) ...[
                if (i > 0) const SizedBox(width: 4),
                Container(
                  width: 4,
                  height: _heightFor(i, _controller.value),
                  decoration: BoxDecoration(
                    color: AppColors.accent,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ],
            ],
          );
        },
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
  final VoidCallback onTap;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        BouncyButton(
          onTap: onTap,
          pressedScale: 0.92,
          child: Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
              boxShadow: AppColors.floatingShadow,
            ),
            child: Icon(icon, color: iconColor, size: 28),
          ),
        ),
        const SizedBox(height: Spacing.sm),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
