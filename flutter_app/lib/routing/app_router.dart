import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/magic_link_screen.dart';
import '../features/auth/passkey_screen.dart';
import '../features/chat/chat_screen.dart';
import '../features/home/dashboard_screen.dart';
import '../features/insights/insights_screen.dart';
import '../features/voice/voice_overlay.dart';
import '../shell/homebase_shell.dart';
import '../state/app_state.dart';
import 'routes.dart';

/// Builds the GoRouter config. Auth state gates everything behind a redirect
/// to the passkey screen.
///
/// Deep links from push notifications and magic-link taps land here. The
/// FCM handler should call `router.go(message.data['deep_link'])`; the
/// app_links handler reads `uri.path` and does the same. Wiring is in PR2.
GoRouter buildAppRouter(WidgetRef ref) {
  return GoRouter(
    initialLocation: Routes.home,
    debugLogDiagnostics: false,
    redirect: (context, state) {
      final isAuthed = ref.read(authControllerProvider);
      final goingToAuth = state.matchedLocation.startsWith('/auth/');

      if (!isAuthed && !goingToAuth) {
        return Routes.authPasskey;
      }
      if (isAuthed && goingToAuth) {
        return Routes.home;
      }
      return null;
    },
    routes: [
      // Auth flows
      GoRoute(
        path: Routes.authPasskey,
        builder: (context, state) => const PasskeyScreen(),
      ),
      GoRoute(
        path: Routes.authMagicLink,
        builder: (context, state) => const MagicLinkScreen(),
      ),

      // Voice capture (modal, floats above the shell)
      GoRoute(
        path: Routes.voice,
        pageBuilder: (context, state) => const MaterialPage<void>(
          fullscreenDialog: true,
          child: VoiceOverlay(),
        ),
      ),

      // Tab shell — each branch keeps its own state and nav stack.
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            HomebaseShell(navigationShell: navigationShell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.home,
                builder: (context, state) => const DashboardScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.agents,
                builder: (context, state) => const ChatScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.insights,
                builder: (context, state) => const InsightsScreen(),
              ),
            ],
          ),
        ],
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      body: Center(child: Text('Route not found: ${state.matchedLocation}')),
    ),
  );
}
