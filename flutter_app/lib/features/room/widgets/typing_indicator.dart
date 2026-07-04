import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../theme/colors.dart';

/// Three softly pulsing dots shown while the assistant is responding.
class TypingIndicator extends StatefulWidget {
  const TypingIndicator({super.key});

  @override
  State<TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<TypingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1100),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          return Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (var i = 0; i < 3; i++) ...[
                if (i > 0) const SizedBox(width: 5),
                _Dot(phase: _controller.value, index: i),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  const _Dot({required this.phase, required this.index});

  final double phase;
  final int index;

  @override
  Widget build(BuildContext context) {
    // Each dot pulses on a sine wave, offset a third of a cycle apart.
    final t = (phase - index * 0.18) * 2 * math.pi;
    final wave = (math.sin(t) + 1) / 2;
    final opacity = 0.25 + wave * 0.55;
    final lift = wave * -2.5;

    return Transform.translate(
      offset: Offset(0, lift),
      child: Container(
        width: 7,
        height: 7,
        decoration: BoxDecoration(
          color: AppColors.textMuted.withValues(alpha: opacity),
          shape: BoxShape.circle,
        ),
      ),
    );
  }
}
