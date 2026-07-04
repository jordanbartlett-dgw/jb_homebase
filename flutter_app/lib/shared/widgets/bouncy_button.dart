import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Tactile press: scales to [pressedScale] on pointer-down, springs back
/// with a slight easeOutBack overshoot on release. Fires light haptic
/// feedback so presses feel physical. Wrap any card or control.
class BouncyButton extends StatefulWidget {
  const BouncyButton({
    super.key,
    required this.child,
    this.onTap,
    this.pressedScale = 0.96,
    this.haptics = true,
  });

  final Widget child;
  final VoidCallback? onTap;
  final double pressedScale;
  final bool haptics;

  @override
  State<BouncyButton> createState() => _BouncyButtonState();
}

class _BouncyButtonState extends State<BouncyButton>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 110),
    reverseDuration: const Duration(milliseconds: 220),
  );

  late final Animation<double> _scale =
      Tween(begin: 1.0, end: widget.pressedScale).animate(
    CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOut,
      reverseCurve: Curves.easeOutBack,
    ),
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _down(TapDownDetails _) => _controller.forward();

  void _up(TapUpDetails _) {
    _controller.reverse();
    if (widget.haptics) HapticFeedback.lightImpact();
    widget.onTap?.call();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTapDown: _down,
      onTapUp: _up,
      onTapCancel: _controller.reverse,
      child: ScaleTransition(scale: _scale, child: widget.child),
    );
  }
}
