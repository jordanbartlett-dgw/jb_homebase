import 'package:flutter/material.dart';

import '../../../theme/app_theme.dart';

/// Three-dot typing indicator with a gentle staggered pulse, tinted per
/// agent so the "thinking" state carries the agent's identity.
class TypingIndicator extends StatefulWidget {
  const TypingIndicator({super.key, required this.tint});

  final Color tint;

  @override
  State<TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<TypingIndicator>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 5),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(AppTheme.radiusBubble),
            topRight: Radius.circular(AppTheme.radiusBubble),
            bottomRight: Radius.circular(AppTheme.radiusBubble),
            bottomLeft: Radius.circular(4),
          ),
        ),
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, _) => Row(
            mainAxisSize: MainAxisSize.min,
            children: List.generate(3, (i) {
              // Stagger each dot a third of a cycle apart.
              final t = (_controller.value + i / 3) % 1.0;
              final pulse = (t < 0.5 ? t : 1 - t) * 2; // triangle wave 0..1
              return Container(
                margin: const EdgeInsets.symmetric(horizontal: 3),
                width: 7,
                height: 7,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: widget.tint.withValues(alpha: 0.35 + 0.5 * pulse),
                ),
              );
            }),
          ),
        ),
      ),
    );
  }
}
