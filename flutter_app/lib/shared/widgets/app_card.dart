import 'package:flutter/material.dart';

import '../../theme/colors.dart';
import '../../theme/spacing.dart';

/// Standard rounded card with subtle shadow. Used on Today and elsewhere.
class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.onTap,
    this.padding = const EdgeInsets.all(Spacing.lg),
  });

  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Ink(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(14),
            boxShadow: const [
              BoxShadow(color: AppColors.shadow, blurRadius: 12, offset: Offset(0, 2)),
            ],
          ),
          child: Padding(padding: padding, child: child),
        ),
      ),
    );
  }
}
