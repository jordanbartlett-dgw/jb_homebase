import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../theme/colors.dart';
import 'pressable.dart';

/// The mic is reachable from every surface. Tapping pushes the voice
/// overlay modal route.
class MicButton extends StatelessWidget {
  const MicButton({super.key, this.size = 48});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Pressable(
      onTap: () => context.push(Routes.voice),
      pressedScale: 0.92,
      child: Container(
        width: size,
        height: size,
        decoration: const BoxDecoration(
          color: AppColors.accent,
          shape: BoxShape.circle,
          boxShadow: AppColors.cardShadow,
        ),
        child: const Icon(Icons.mic, color: AppColors.onAccent, size: 22),
      ),
    );
  }
}
