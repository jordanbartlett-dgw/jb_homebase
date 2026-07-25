import 'package:flutter/material.dart';

/// Design tokens for the JB Homebase palette.
///
/// The brand is intentionally monochrome: paper, ink, and a short neutral
/// ramp. Cobalt is the only non-semantic accent and is reserved for action,
/// selection, and live state.
class AppColors {
  const AppColors._();

  // Monochrome foundation
  static const Color white = Color(0xFFFFFFFF);
  static const Color paper = Color(0xFFF7F7F5);
  static const Color neutral100 = Color(0xFFEDEDE9);
  static const Color neutral300 = Color(0xFFC9C9C3);
  static const Color neutral500 = Color(0xFF777772);
  static const Color neutral700 = Color(0xFF3F3F3B);
  static const Color ink = Color(0xFF111111);
  static const Color nearBlack = Color(0xFF080808);
  static const Color charcoal = Color(0xFF141416);
  static const Color graphite = Color(0xFF202024);

  // Brand accent
  static const Color cobalt = Color(0xFF3157F6);
  static const Color cobaltBright = Color(0xFF7D96FF);
  static const Color cobaltSoft = Color(0xFFE5EAFF);

  // Status (used sparingly)
  static const Color warning = Color(0xFFB8860B);
  static const Color error = Color(0xFFB3543F);
  static const Color success = Color(0xFF4F7A52);

  static const Color shadow = Color(0x12000000);
}
