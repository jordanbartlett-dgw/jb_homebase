import 'package:flutter/material.dart';

import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import 'mic_button.dart';

/// Persistent bottom action bar. Surfaces vary by screen:
/// - On Today: mic / "Chat with Claw Main" / pencil
/// - Inside a Room: mic / composer / send
class BottomActionBar extends StatelessWidget {
  const BottomActionBar({
    super.key,
    required this.center,
    this.trailing,
    this.showMic = true,
  });

  /// The center action — a "Chat with Claw Main" CTA on Today, or a composer
  /// field inside a Room.
  final Widget center;
  final Widget? trailing;
  final bool showMic;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.background,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: Spacing.lg, vertical: Spacing.md),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            if (showMic) ...[
              const MicButton(),
              const SizedBox(width: Spacing.md),
            ],
            Expanded(child: center),
            if (trailing != null) ...[
              const SizedBox(width: Spacing.md),
              trailing!,
            ],
          ],
        ),
      ),
    );
  }
}
