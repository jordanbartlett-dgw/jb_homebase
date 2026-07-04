import 'package:http/http.dart' as http;

/// Stub HTTP client for the gateway. No real calls in v1 scaffold.
///
/// PR2 swaps this for an `EventStreamDecoder`-backed implementation that
/// streams agent events (SSE or chunked NDJSON, decided on the backend side).
class ApiClient {
  ApiClient({http.Client? inner, this.baseUrl = 'https://gateway.jbhomebase.app'})
      : _inner = inner ?? http.Client();

  final http.Client _inner;
  final String baseUrl;

  // TODO(backend): wire `/api/today/cards` with auth header.
  Future<void> fetchTodayCards() async {
    // Intentionally no-op for the scaffold.
  }

  // TODO(backend): wire `/api/rooms/:roomId/conversations`.
  Future<void> fetchActiveConversation(String roomId) async {}

  // TODO(backend): wire `/api/rooms/:roomId/messages` with streaming response.
  Future<void> sendMessage({required String roomId, required String body}) async {}

  // TODO(backend): wire multipart voice upload to `/api/rooms/:roomId/voice`.
  Future<void> uploadVoice({required String roomId, required String filePath}) async {}

  void dispose() {
    _inner.close();
  }
}
