import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';

void main() {
  // TODO(backend): initialize Firebase, request push permission, register
  // FCM token with the gateway. Wired in PR2 / push notifications work.
  runApp(
    const ProviderScope(child: JordanClawApp()),
  );
}
