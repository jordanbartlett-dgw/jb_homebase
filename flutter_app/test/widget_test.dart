import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:jb_homebase_app/app.dart';

void main() {
  testWidgets('App boots without crashing', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: JBHomebaseApp()),
    );
    // Initial frame should land on the passkey screen because auth is false.
    // pumpAndSettle advances fake time so the staggered Entrance timers fire.
    await tester.pumpAndSettle();
    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.text('Sign in with passkey'), findsOneWidget);
  });
}
