import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../theme/colors.dart';

/// The mic is reachable from every surface. Tapping pushes the voice
/// overlay modal route.
class MicButton extends StatelessWidget {
  const MicButton({super.key, this.size = 48});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.accent,
      shape: const CircleBorder(),
      elevation: 0,
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: () => context.push(Routes.voice),
        child: SizedBox(
          width: size,
          height: size,
          child: const Icon(Icons.mic, color: AppColors.onAccent, size: 22),
        ),
      ),
    );
  }
}
