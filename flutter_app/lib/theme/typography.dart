import 'package:flutter/material.dart';

import 'colors.dart';

/// M3 type scale with generous line-height and weight bumps for hierarchy.
///
/// Uses the system font (SF on iOS). Line height is 1.5 for body copy to
/// match the Granola-influenced reading rhythm.
class AppTypography {
  const AppTypography._();

  static TextTheme buildTextTheme() {
    const base = TextStyle(color: AppColors.textPrimary, height: 1.5);

    return const TextTheme(
      displaySmall: TextStyle(
        fontSize: 32,
        fontWeight: FontWeight.w600,
        color: AppColors.textPrimary,
        height: 1.25,
      ),
      headlineMedium: TextStyle(
        fontSize: 24,
        fontWeight: FontWeight.w600,
        color: AppColors.textPrimary,
        height: 1.3,
      ),
      titleLarge: TextStyle(
        fontSize: 20,
        fontWeight: FontWeight.w600,
        color: AppColors.textPrimary,
        height: 1.35,
      ),
      titleMedium: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w600,
        color: AppColors.textPrimary,
        height: 1.4,
      ),
      bodyLarge: TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w400,
        color: AppColors.textPrimary,
        height: 1.5,
      ),
      bodyMedium: TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.w400,
        color: AppColors.textSecondary,
        height: 1.5,
      ),
      bodySmall: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w400,
        color: AppColors.textMuted,
        height: 1.4,
      ),
      labelLarge: TextStyle(
        fontSize: 14,
        fontWeight: FontWeight.w600,
        color: AppColors.textPrimary,
        height: 1.4,
      ),
      labelSmall: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w500,
        color: AppColors.textMuted,
        height: 1.4,
        letterSpacing: 0.4,
      ),
    ).apply(bodyColor: base.color);
  }
}
