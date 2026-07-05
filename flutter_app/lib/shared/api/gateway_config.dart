/// Compile-time gateway configuration, injected at build time:
///
///   flutter run \
///     --dart-define=GATEWAY_URL=https://`railway-host` \
///     --dart-define=CLAW_APP_TOKEN=`token`
///
/// When both values are present the app runs live against the Jordan Claw
/// gateway and boots signed in (the static token IS the interim auth, per
/// the PR2 plan). Without them every surface stays on mock data — the
/// design-build behavior, which is also what widget tests exercise.
class GatewayConfig {
  const GatewayConfig._();

  static const String baseUrl = String.fromEnvironment('GATEWAY_URL');
  static const String appToken = String.fromEnvironment('CLAW_APP_TOKEN');
  static const bool isLive = baseUrl != '' && appToken != '';
}
