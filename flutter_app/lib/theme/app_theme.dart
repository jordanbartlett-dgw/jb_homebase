import 'package:flutter/cupertino.dart' show CupertinoPageTransitionsBuilder;
import 'package:flutter/material.dart';

import 'colors.dart';
import 'typography.dart';

/// Assembles ThemeData for JB Homebase.
///
/// Light and dark are built from the same monochrome recipe. Cobalt is the
/// single brand accent; press feedback comes from scale + haptics.
class AppTheme {
  const AppTheme._();

  /// Shared radii and paddings so components stay consistent.
  static const double radiusCard = 18;
  static const double radiusBubble = 18;
  static const EdgeInsets pagePadding = EdgeInsets.symmetric(horizontal: 24);

  static ThemeData get light => _build(Brightness.light);
  static ThemeData get dark => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    final isDark = brightness == Brightness.dark;

    final bg = isDark ? AppColors.nearBlack : AppColors.paper;
    final surface = isDark ? AppColors.charcoal : AppColors.white;
    final ink = isDark ? AppColors.white : AppColors.ink;
    final muted = isDark ? AppColors.neutral300 : AppColors.neutral500;
    final accent = isDark ? AppColors.cobaltBright : AppColors.cobalt;
    final inverseSurface = isDark ? AppColors.white : AppColors.nearBlack;
    final onInverseSurface = isDark ? AppColors.nearBlack : AppColors.white;

    final scheme = ColorScheme(
      brightness: brightness,
      primary: accent,
      onPrimary: isDark ? AppColors.nearBlack : AppColors.white,
      secondary: accent,
      onSecondary: isDark ? AppColors.nearBlack : AppColors.white,
      surface: surface,
      onSurface: ink,
      surfaceContainerHighest: isDark ? AppColors.graphite : AppColors.neutral100,
      error: AppColors.error,
      onError: AppColors.white,
      outline: isDark ? AppColors.neutral700 : AppColors.neutral300,
      outlineVariant: isDark ? AppColors.graphite : AppColors.neutral100,
      inverseSurface: inverseSurface,
      onInverseSurface: onInverseSurface,
      inversePrimary: isDark ? AppColors.cobalt : AppColors.cobaltBright,
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
          side: BorderSide(color: scheme.outlineVariant),
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
        color: scheme.outlineVariant,
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
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: ink,
          minimumSize: const Size.fromHeight(52),
          side: BorderSide(color: scheme.outline),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
          textStyle: textTheme.labelLarge,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: scheme.outlineVariant),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: accent, width: 1.5),
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
        ),
      ),
    );
  }

  /// Small lift for floating controls. Most surfaces use a hairline instead.
  static List<BoxShadow> softShadow(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return [
      BoxShadow(
        color: Colors.black.withValues(alpha: isDark ? 0.28 : 0.07),
        blurRadius: 14,
        offset: const Offset(0, 5),
      ),
    ];
  }
}
