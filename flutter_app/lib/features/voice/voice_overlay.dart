import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import 'voice_preview.dart';

/// Full-screen voice capture modal. UI only — no real audio capture in v1
/// scaffold. Real `record` integration lands in PR2.
class VoiceOverlay extends StatelessWidget {
  const VoiceOverlay({super.key});

  void _stopAndPreview(BuildContext context) {
    // TODO(backend): stop `record` session, hand the audio file to the preview.
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
                  Text('Recording', style: textTheme.titleMedium),
                  const SizedBox(width: 48),
                ],
              ),
            ),
            const Spacer(),
            // Static placeholder waveform. Real-time amplitude rendering via
            // `audio_waveforms` lands when capture is wired in PR2.
            const _StaticWaveform(),
            const SizedBox(height: Spacing.lg),
            Text('0:08', style: textTheme.titleLarge),
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
                    icon: Icons.stop,
                    label: 'Stop',
                    color: AppColors.accent,
                    iconColor: AppColors.onAccent,
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

class _StaticWaveform extends StatelessWidget {
  const _StaticWaveform();

  @override
  Widget build(BuildContext context) {
    // Faux waveform — sized bars at a sine-shaped curve so it feels alive.
    const heights = [
      8.0, 14.0, 22.0, 30.0, 40.0, 48.0, 52.0, 48.0, 40.0, 30.0,
      22.0, 14.0, 18.0, 28.0, 38.0, 46.0, 50.0, 46.0, 38.0, 28.0,
      18.0, 12.0, 8.0,
    ];

    return SizedBox(
      height: 64,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          for (final h in heights) ...[
            Container(
              width: 4,
              height: h,
              decoration: BoxDecoration(
                color: AppColors.accent,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(width: 4),
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
  });

  final IconData icon;
  final String label;
  final Color color;
  final Color iconColor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Material(
          color: color,
          shape: const CircleBorder(),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: onTap,
            child: SizedBox(
              width: 64,
              height: 64,
              child: Icon(icon, color: iconColor, size: 28),
            ),
          ),
        ),
        const SizedBox(height: Spacing.sm),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
