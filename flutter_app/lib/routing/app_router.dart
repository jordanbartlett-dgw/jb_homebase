import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/magic_link_screen.dart';
import '../features/auth/passkey_screen.dart';
import '../features/room/room_screen.dart';
import '../features/room/tabs/chat_tab.dart';
import '../features/room/tabs/context_tab.dart';
import '../features/room/tabs/history_tab.dart';
import '../features/today/today_screen.dart';
import '../features/voice/voice_overlay.dart';
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
    initialLocation: Routes.today,
    debugLogDiagnostics: false,
    redirect: (context, state) {
      final isAuthed = ref.read(authControllerProvider);
      final goingToAuth = state.matchedLocation.startsWith('/auth/');

      if (!isAuthed && !goingToAuth) {
        return Routes.authPasskey;
      }
      if (isAuthed && goingToAuth) {
        return Routes.today;
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

      // Today
      GoRoute(
        path: Routes.today,
        builder: (context, state) => const TodayScreen(),
      ),

      // Voice capture (modal route)
      GoRoute(
        path: Routes.voice,
        pageBuilder: (context, state) => const MaterialPage<void>(
          fullscreenDialog: true,
          child: VoiceOverlay(),
        ),
      ),

      // Room (with nested tabs)
      GoRoute(
        path: '/room/:roomId',
        redirect: (context, state) {
          final roomId = state.pathParameters['roomId'];
          if (roomId == null) return Routes.today;
          // If someone lands directly on `/room/:id`, default to chat tab.
          // Compare against the full target path, not matchedLocation:
          // during parent-route evaluation matchedLocation is only the
          // partially matched '/room/:id', which would hijack navigation
          // to the context/history sub-routes back to chat.
          if (state.uri.path == '/room/$roomId') {
            return Routes.roomChat(roomId);
          }
          return null;
        },
        builder: (context, state) {
          final roomId = state.pathParameters['roomId']!;
          return RoomScreen(roomId: roomId, child: const ChatTab());
        },
        routes: [
          GoRoute(
            path: 'chat',
            builder: (context, state) {
              final roomId = state.pathParameters['roomId']!;
              return RoomScreen(roomId: roomId, child: const ChatTab());
            },
          ),
          GoRoute(
            path: 'context',
            builder: (context, state) {
              final roomId = state.pathParameters['roomId']!;
              return RoomScreen(roomId: roomId, child: const ContextTab());
            },
          ),
          GoRoute(
            path: 'history',
            builder: (context, state) {
              final roomId = state.pathParameters['roomId']!;
              return RoomScreen(roomId: roomId, child: const HistoryTab());
            },
          ),
        ],
      ),
    ],
    errorBuilder: (context, state) => Scaffold(
      body: Center(child: Text('Route not found: ${state.matchedLocation}')),
    ),
  );
}
