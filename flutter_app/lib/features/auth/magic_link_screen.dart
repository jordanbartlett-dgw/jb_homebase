import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../state/app_state.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';

class MagicLinkScreen extends ConsumerStatefulWidget {
  const MagicLinkScreen({super.key});

  @override
  ConsumerState<MagicLinkScreen> createState() => _MagicLinkScreenState();
}

class _MagicLinkScreenState extends ConsumerState<MagicLinkScreen> {
  final TextEditingController _emailController = TextEditingController();
  bool _sent = false;

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  void _sendLink() {
    // TODO(backend): POST /api/auth/magic-link with email, server emails the
    // signed token. Tap on email opens auth.jbhomebase.app universal link,
    // app_links delivers the URI here, we exchange for a session.
    setState(() => _sent = true);
  }

  void _completeSignIn() {
    ref.read(authControllerProvider.notifier).signIn();
    context.go(Routes.today);
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Magic link')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(Spacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Sign in by email', style: textTheme.titleLarge),
              const SizedBox(height: Spacing.sm),
              Text(
                'Recovery path when a passkey is not available. The link from '
                'auth.jbhomebase.app opens this app and signs you in.',
                style: textTheme.bodyMedium,
              ),
              const SizedBox(height: Spacing.xl),
              TextField(
                controller: _emailController,
                keyboardType: TextInputType.emailAddress,
                decoration: const InputDecoration(hintText: 'you@example.com'),
              ),
              const SizedBox(height: Spacing.lg),
              FilledButton(
                onPressed: _sendLink,
                child: const Text('Send link'),
              ),
              if (_sent) ...[
                const SizedBox(height: Spacing.xl),
                Container(
                  padding: const EdgeInsets.all(Spacing.md),
                  decoration: BoxDecoration(
                    color: AppColors.surfaceVariant,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    'Sent. In the real app you would tap the email link to finish '
                    'signing in. Tap below to simulate the tap.',
                    style: textTheme.bodySmall,
                  ),
                ),
                const SizedBox(height: Spacing.md),
                OutlinedButton(
                  onPressed: _completeSignIn,
                  child: const Text('Simulate link tap'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
