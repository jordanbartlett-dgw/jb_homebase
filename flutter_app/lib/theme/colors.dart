import 'package:flutter/material.dart';

/// Design tokens for the JB Homebase palette.
///
/// Palette philosophy (from the design prototype): deep slates for
/// grounding, warm creams for air, sage as the single accent. Sage is
/// spent deliberately — active states, the digest gradient, and nothing
/// else. Everything else stays quiet.
class AppColors {
  const AppColors._();

  // Core palette
  static const Color cream = Color(0xFFF6F1E7); // warm cream — light bg
  static const Color creamElevated = Color(0xFFFDFAF3); // cards on cream
  static const Color mist = Color(0xFFE8E2D4); // dividers, subtle fills
  static const Color deepSlate = Color(0xFF1B222B); // dark bg / light ink
  static const Color slate = Color(0xFF2A333F); // dark-mode surface
  static const Color slateElevated = Color(0xFF333E4C); // dark-mode cards
  static const Color sage = Color(0xFF9CB39A); // accent on dark bg
  static const Color sageDeep = Color(0xFF64805F); // accent on light bg
  static const Color inkMuted = Color(0xFF6B7280); // secondary text (light)
  static const Color creamMuted = Color(0xFFB4AFA3); // secondary text (dark)

  /// Digest gradient — the one loud moment on the dashboard.
  static const List<Color> digestGradientLight = [
    Color(0xFF64805F),
    Color(0xFF3C4A3E),
  ];
  static const List<Color> digestGradientDark = [
    Color(0xFF4C6249),
    Color(0xFF232B26),
  ];

  // ---- Light-mode aliases used by static call sites (auth, voice) ----

  // Surface
  static const Color background = cream;
  static const Color surface = creamElevated;
  static const Color surfaceVariant = mist;

  // Text hierarchy
  static const Color textPrimary = deepSlate;
  static const Color textSecondary = Color(0xFF4C5560);
  static const Color textMuted = inkMuted;
  static const Color textDisabled = Color(0xFFA9ACB0);

  // Accent
  static const Color accent = sageDeep;
  static const Color onAccent = cream;

  /// Pressed/darkened accent for interactive feedback on filled controls.
  static const Color accentPressed = Color(0xFF52694E);

  /// Soft sage wash for icon plates, selected states, and highlights.
  static const Color accentSoft = Color(0xFFDEE4D9);

  // Status (used sparingly)
  static const Color warning = Color(0xFFB8860B);
  static const Color error = Color(0xFFB3543F);
  static const Color success = Color(0xFF4F7A52);

  // Borders / dividers
  static const Color border = mist;
  static const Color shadow = Color(0x141B222B);

  /// Soft, diffuse card lift (slate-tinted, never pure black).
  static const List<BoxShadow> cardShadow = [
    BoxShadow(
      color: Color(0x141B222B),
      blurRadius: 30,
      offset: Offset(0, 12),
    ),
  ];

  /// Stronger lift for floating elements (pill nav, overlays).
  static const List<BoxShadow> floatingShadow = [
    BoxShadow(
      color: Color(0x1F1B222B),
      blurRadius: 34,
      offset: Offset(0, 14),
    ),
  ];
}
