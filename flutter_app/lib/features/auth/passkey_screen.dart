import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../shared/widgets/entrance.dart';
import '../../state/app_state.dart';
import '../../theme/spacing.dart';

/// Passkey is the primary sign-in across all devices. Magic-link recovery
/// sits behind the "Having trouble?" link, not as a co-equal option.
class PasskeyScreen extends ConsumerWidget {
  const PasskeyScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final textTheme = Theme.of(context).textTheme;

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(Spacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Spacer(flex: 2),
              Entrance(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(
                        color: theme.colorScheme.inverseSurface,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                          color: theme.colorScheme.primary,
                          width: 1.5,
                        ),
                      ),
                      child: Center(
                        child: Text(
                          'JC',
                          style: TextStyle(
                            color: theme.colorScheme.onInverseSurface,
                            fontWeight: FontWeight.w700,
                            fontSize: 20,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: Spacing.xl),
                    Text('Jordan Claw', style: textTheme.displaySmall),
                    const SizedBox(height: Spacing.sm),
                    Text(
                      'Your agents, in your pocket.',
                      style: textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
              const Spacer(),
              Entrance(
                index: 2,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    FilledButton.icon(
                      onPressed: () {
                        // TODO(backend): trigger `passkeys` flow, exchange with
                        // gateway for a session token, store via
                        // `flutter_secure_storage`.
                        ref.read(authControllerProvider.notifier).signIn();
                        context.go(Routes.home);
                      },
                      icon: const Icon(Icons.fingerprint, size: 20),
                      label: const Text('Sign in with passkey'),
                    ),
                    const SizedBox(height: Spacing.lg),
                    Center(
                      child: TextButton(
                        onPressed: () => context.go(Routes.authMagicLink),
                        style: TextButton.styleFrom(
                          foregroundColor: theme.colorScheme.outline,
                        ),
                        child: const Text('Having trouble?'),
                      ),
                    ),
                  ],
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
