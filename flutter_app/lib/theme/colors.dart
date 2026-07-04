import 'package:flutter/material.dart';

/// Design tokens for the Jordan Claw color palette.
///
/// Background is a warm off-white (Granola direction). Accent is a deep
/// warm moss with a yellow lean — locked by Jordan as `#6B7A3F`.
class AppColors {
  const AppColors._();

  // Surface
  static const Color background = Color(0xFFF7F5F0);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color surfaceVariant = Color(0xFFEFEDE6);

  // Text hierarchy (near-black base)
  static const Color textPrimary = Color(0xFF1A1815);
  static const Color textSecondary = Color(0xFF4A4742);
  static const Color textMuted = Color(0xFF6B6B6B);
  static const Color textDisabled = Color(0xFFA8A6A1);

  // Accent — locked warm moss
  static const Color accent = Color(0xFF6B7A3F);
  static const Color onAccent = Color(0xFFFFFFFF);

  /// Pressed/darkened accent for interactive feedback on filled controls.
  static const Color accentPressed = Color(0xFF57652F);

  /// Soft moss wash for icon plates, selected states, and highlights.
  static const Color accentSoft = Color(0xFFE9ECDD);

  // Status (used sparingly)
  static const Color warning = Color(0xFFB8860B);
  static const Color error = Color(0xFFB04444);
  static const Color success = Color(0xFF4F7A52);

  // Borders / dividers
  static const Color border = Color(0xFFE3E0D8);
  static const Color shadow = Color(0x14000000);

  /// Warm-tinted layered card shadow: a tight key shadow for edge
  /// definition plus a wide ambient wash for lift. Warm hue (not pure
  /// black) so cards sit naturally on the off-white background.
  static const List<BoxShadow> cardShadow = [
    BoxShadow(
      color: Color(0x0A2A2418),
      blurRadius: 3,
      offset: Offset(0, 1),
    ),
    BoxShadow(
      color: Color(0x122A2418),
      blurRadius: 16,
      offset: Offset(0, 6),
    ),
  ];

  /// Stronger lift for floating elements (overlays, raised buttons).
  static const List<BoxShadow> floatingShadow = [
    BoxShadow(
      color: Color(0x0F2A2418),
      blurRadius: 4,
      offset: Offset(0, 2),
    ),
    BoxShadow(
      color: Color(0x1F2A2418),
      blurRadius: 24,
      offset: Offset(0, 10),
    ),
  ];
}
