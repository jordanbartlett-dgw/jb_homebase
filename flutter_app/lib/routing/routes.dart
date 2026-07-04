/// Route name and path constants.
///
/// Keep route paths in one place so deep-link handlers (FCM tap, app_links)
/// stay aligned with the router config.
class Routes {
  const Routes._();

  static const String today = '/';

  // Room (path uses :roomId; in v1 only `claw-main` is active).
  static String room(String roomId) => '/room/$roomId';
  static String roomChat(String roomId) => '/room/$roomId/chat';
  static String roomContext(String roomId) => '/room/$roomId/context';
  static String roomHistory(String roomId) => '/room/$roomId/history';

  // Auth
  static const String authPasskey = '/auth/passkey';
  static const String authMagicLink = '/auth/magic-link';

  // Voice capture overlay (modal)
  static const String voice = '/voice';
}
