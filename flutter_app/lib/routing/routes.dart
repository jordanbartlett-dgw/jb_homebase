/// Route name and path constants.
///
/// Keep route paths in one place so deep-link handlers (FCM tap, app_links)
/// stay aligned with the router config.
class Routes {
  const Routes._();

  // Shell branches
  static const String home = '/home';
  static const String agents = '/agents';
  static const String insights = '/insights';

  // Auth
  static const String authPasskey = '/auth/passkey';
  static const String authMagicLink = '/auth/magic-link';

  // Voice capture overlay (modal)
  static const String voice = '/voice';
}
