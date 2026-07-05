import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// JB Homebase type system.
///
/// Display = Playfair Display, used with restraint: the greeting and card
/// headlines. Everything functional = Inter. `titleSmall` is the eyebrow
/// style — uppercase it at the call site.
class AppTypography {
  const AppTypography._();

  static TextTheme buildTextTheme({
    required Color ink,
    required Color muted,
  }) {
    return TextTheme(
      displayLarge: GoogleFonts.playfairDisplay(
        fontSize: 40,
        fontWeight: FontWeight.w600,
        color: ink,
        height: 1.1,
      ),
      displayMedium: GoogleFonts.playfairDisplay(
        fontSize: 30,
        fontWeight: FontWeight.w600,
        color: ink,
        height: 1.15,
      ),
      displaySmall: GoogleFonts.playfairDisplay(
        fontSize: 26,
        fontWeight: FontWeight.w600,
        color: ink,
        height: 1.2,
      ),
      headlineMedium: GoogleFonts.playfairDisplay(
        fontSize: 24,
        fontWeight: FontWeight.w600,
        color: ink,
        height: 1.2,
      ),
      headlineSmall: GoogleFonts.playfairDisplay(
        fontSize: 22,
        fontWeight: FontWeight.w600,
        color: ink,
      ),
      titleLarge: GoogleFonts.inter(
        fontSize: 18,
        fontWeight: FontWeight.w600,
        color: ink,
        height: 1.35,
      ),
      titleMedium: GoogleFonts.inter(
        fontSize: 16,
        fontWeight: FontWeight.w600,
        color: ink,
      ),
      // Eyebrow labels — uppercase in usage.
      titleSmall: GoogleFonts.inter(
        fontSize: 13,
        fontWeight: FontWeight.w600,
        color: muted,
        letterSpacing: 1.2,
      ),
      bodyLarge: GoogleFonts.inter(fontSize: 16, color: ink, height: 1.5),
      bodyMedium: GoogleFonts.inter(fontSize: 14, color: ink, height: 1.5),
      bodySmall: GoogleFonts.inter(fontSize: 12, color: muted),
      labelLarge: GoogleFonts.inter(
        fontSize: 14,
        fontWeight: FontWeight.w600,
        color: ink,
      ),
      labelSmall: GoogleFonts.inter(
        fontSize: 11,
        fontWeight: FontWeight.w600,
        color: muted,
        letterSpacing: 0.6,
      ),
    );
  }
}
