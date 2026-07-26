import 'dart:convert';
import 'dart:io';

Future<void> main() async {
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 8787);
  stdout.writeln('JB Homebase stub listening on http://127.0.0.1:8787');

  await for (final request in server) {
    final path = request.uri.path;
    stdout.writeln('${request.method} $path');
    request.response.headers.contentType = ContentType.json;

    if (request.method == 'GET' && path == '/app/today') {
      _json(request, {
        'date': '2026-07-25',
        'timezone': 'America/Chicago',
        'digest': null,
        'calendar_status': 'available',
        'calendar_message': null,
        'events': <Object>[],
      });
    } else if (request.method == 'GET' && path == '/app/conversations/current') {
      _json(request, null);
    } else if (request.method == 'POST' && path == '/app/messages') {
      final body = jsonDecode(await utf8.decoder.bind(request).join()) as Map<String, dynamic>;
      await Future<void>.delayed(const Duration(milliseconds: 1500));
      _json(request, {
        'agent_slug': body['agent_slug'],
        'reply': 'stub reply for ${body['agent_slug']}',
        'conversation_id': 'stub-conversation',
      });
    } else if (request.method == 'POST' && path == '/voice/transcribe') {
      await request.drain<void>();
      _json(request, {'transcript': 'stub voice transcript'});
    } else if (request.method == 'POST' && path == '/voice/messages') {
      final body = jsonDecode(await utf8.decoder.bind(request).join()) as Map<String, dynamic>;
      _json(request, {
        'transcript': body['transcript'],
        'agent_slug': 'claw-main',
        'reply': 'stub voice reply',
      });
    } else {
      request.response.statusCode = HttpStatus.notFound;
      _json(request, {'detail': 'not found'});
    }
  }
}

void _json(HttpRequest request, Object? body) {
  request.response.write(jsonEncode(body));
  request.response.close();
}
