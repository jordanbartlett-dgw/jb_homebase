import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:jb_homebase_app/features/chat/widgets/streaming_response.dart';
import 'package:jb_homebase_app/theme/app_theme.dart';

Widget _subject({
  required String status,
  required String partialText,
}) {
  return MaterialApp(
    theme: AppTheme.light,
    home: Scaffold(
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          StreamingResponse(
            status: status,
            partialText: partialText,
          ),
        ],
      ),
    ),
  );
}

void main() {
  testWidgets('moves from safe activity into partial Markdown output', (tester) async {
    await tester.pumpWidget(
      _subject(status: 'Checking your calendar', partialText: ''),
    );

    expect(find.text('Checking your calendar'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('streaming-response-bubble')),
      findsNothing,
    );

    await tester.pumpWidget(
      _subject(
        status: 'Writing response',
        partialText: '**Today:** Board call at 10:00.',
      ),
    );
    await tester.pump();

    expect(find.text('Writing response'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('streaming-response-bubble')),
      findsOneWidget,
    );
    expect(
      find.textContaining('Today:', findRichText: true),
      findsOneWidget,
    );
    expect(
      find.textContaining('Board call at 10:00.', findRichText: true),
      findsOneWidget,
    );
    expect(find.textContaining('private reasoning'), findsNothing);
  });
}
