import 'package:flutter/cupertino.dart' show CupertinoPageTransitionsBuilder;
import 'package:flutter/material.dart';

import 'colors.dart';
import 'typography.dart';

/// Assembles ThemeData for JB Homebase.
///
/// Light and dark are built from the same recipe; sage is the single
/// accent and everything else stays quiet. Ripple is disabled globally —
/// press feedback comes from scale + haptics (see BouncyButton).
class AppTheme {
  const AppTheme._();

  /// Shared radii and paddings so components stay consistent.
  static const double radiusCard = 24;
  static const double radiusBubble = 20;
  static const EdgeInsets pagePadding = EdgeInsets.symmetric(horizontal: 24);

  static ThemeData get light => _build(Brightness.light);
  static ThemeData get dark => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    final isDark = brightness == Brightness.dark;

    final bg = isDark ? AppColors.deepSlate : AppColors.cream;
    final surface = isDark ? AppColors.slate : AppColors.creamElevated;
    final ink = isDark ? AppColors.cream : AppColors.deepSlate;
    final muted = isDark ? AppColors.creamMuted : AppColors.inkMuted;
    final accent = isDark ? AppColors.sage : AppColors.sageDeep;

    final scheme = ColorScheme(
      brightness: brightness,
      primary: accent,
      onPrimary: isDark ? AppColors.deepSlate : AppColors.cream,
      secondary: AppColors.sage,
      onSecondary: AppColors.deepSlate,
      surface: surface,
      onSurface: ink,
      surfaceContainerHighest:
          isDark ? AppColors.slateElevated : AppColors.mist,
      error: AppColors.error,
      onError: AppColors.cream,
      outline: muted.withValues(alpha: 0.4),
    );

    final textTheme = AppTypography.buildTextTheme(ink: ink, muted: muted);

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: bg,
      textTheme: textTheme,
      // iOS feel: Cupertino slide transitions, no Android ink ripple.
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.android: CupertinoPageTransitionsBuilder(),
        },
      ),
      splashFactory: NoSplash.splashFactory,
      splashColor: Colors.transparent,
      highlightColor: Colors.transparent,
      cardTheme: CardThemeData(
        color: surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radiusCard),
        ),
        margin: EdgeInsets.zero,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: bg,
        foregroundColor: ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleTextStyle: textTheme.headlineSmall,
        iconTheme: IconThemeData(color: ink),
      ),
      dividerTheme: DividerThemeData(
        color: scheme.outline.withValues(alpha: 0.25),
        thickness: 1,
        space: 1,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: accent,
          foregroundColor: scheme.onPrimary,
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(26),
          ),
          textStyle: textTheme.labelLarge,
        ),
      ),
    );
  }

  /// Soft, diffuse drop shadow used on elevated cards. Kept here so every
  /// card lifts identically.
  static List<BoxShadow> softShadow(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return [
      BoxShadow(
        color: (isDark ? Colors.black : AppColors.deepSlate)
            .withValues(alpha: isDark ? 0.35 : 0.08),
        blurRadius: 30,
        offset: const Offset(0, 12),
      ),
    ];
  }
}
