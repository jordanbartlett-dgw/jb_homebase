import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../shared/api/api_client.dart';

/// Shared gateway client — one connection pool for the whole app session.
final apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient();
  ref.onDispose(client.dispose);
  return client;
});
