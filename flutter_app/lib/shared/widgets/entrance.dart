import 'package:flutter/material.dart';

import '../../theme/motion.dart';

/// Fade-up entrance for list items and screen content.
///
/// Pass an [index] to stagger siblings: each step adds [Motion.staggerStep]
/// of delay, so a column of cards cascades in instead of popping at once.
/// Plays once on mount — rebuilds do not retrigger it.
class Entrance extends StatefulWidget {
  const Entrance({super.key, required this.child, this.index = 0});

  final Widget child;
  final int index;

  @override
  State<Entrance> createState() => _EntranceState();
}

class _EntranceState extends State<Entrance>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  late final Animation<Offset> _offset;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: Motion.slow);
    final curved = CurvedAnimation(parent: _controller, curve: Motion.enter);
    _opacity = curved;
    _offset = Tween<Offset>(
      begin: const Offset(0, 0.06),
      end: Offset.zero,
    ).animate(curved);

    Future<void>.delayed(Motion.staggerStep * widget.index, () {
      if (mounted) _controller.forward();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacity,
      child: SlideTransition(position: _offset, child: widget.child),
    );
  }
}
