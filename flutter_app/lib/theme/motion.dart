import 'package:flutter/animation.dart';

/// Motion tokens — one vocabulary for every animation in the app.
///
/// Durations follow a 3-step scale. Curves lean on ease-out families so
/// motion starts fast and settles gently, which reads as responsive on iOS.
class Motion {
  const Motion._();

  /// Micro-interactions: press states, icon swaps, chip toggles.
  static const Duration fast = Duration(milliseconds: 140);

  /// Standard transitions: expand/collapse, fades, tab underline.
  static const Duration medium = Duration(milliseconds: 260);

  /// Entrances: cards sliding in, screens settling.
  static const Duration slow = Duration(milliseconds: 420);

  /// Per-item delay for staggered list entrances.
  static const Duration staggerStep = Duration(milliseconds: 60);

  /// Default settle curve. Fast start, soft landing.
  static const Curve ease = Curves.easeOutCubic;

  /// Pronounced settle for entrances — almost all travel happens early.
  static const Curve enter = Curves.easeOutQuint;

  /// Symmetric curve for looping/pulsing animations.
  static const Curve pulse = Curves.easeInOut;
}
