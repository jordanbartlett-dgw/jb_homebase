import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../state/app_state.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';

/// Passkey is the primary sign-in across all devices. Magic-link recovery
/// sits behind the "Having trouble?" link, not as a co-equal option.
class PasskeyScreen extends ConsumerWidget {
  const PasskeyScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final textTheme = Theme.of(context).textTheme;

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(Spacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Spacer(flex: 2),
              Text('Jordan Claw', style: textTheme.displaySmall),
              const SizedBox(height: Spacing.sm),
              Text(
                'Sign in with the passkey on this device.',
                style: textTheme.bodyMedium,
              ),
              const Spacer(),
              FilledButton(
                onPressed: () {
                  // TODO(backend): trigger `passkeys` flow, exchange with gateway
                  // for a session token, store via `flutter_secure_storage`.
                  ref.read(authControllerProvider.notifier).signIn();
                  context.go(Routes.today);
                },
                child: const Text('Sign in with passkey'),
              ),
              const SizedBox(height: Spacing.lg),
              Center(
                child: TextButton(
                  onPressed: () => context.go(Routes.authMagicLink),
                  style: TextButton.styleFrom(foregroundColor: AppColors.textMuted),
                  child: const Text('Having trouble?'),
                ),
              ),
              const Spacer(flex: 2),
            ],
          ),
        ),
      ),
    );
  }
}
