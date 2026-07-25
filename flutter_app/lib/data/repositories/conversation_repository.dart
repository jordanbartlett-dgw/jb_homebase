import '../../shared/api/api_client.dart';
import '../../shared/api/conversation_api_models.dart';
import '../../shared/models/conversation.dart';
import '../../shared/models/message.dart';

class ConversationRepository {
  const ConversationRepository(this._apiClient);

  final ApiClient _apiClient;

  Future<ConversationPage> listConversations({String? before}) async {
    final payload = await _apiClient.listConversations(before: before);
    return ConversationPage(
      conversations: payload.conversations.map(_summary).toList(),
      nextBefore: payload.nextBefore,
    );
  }

  Future<ConversationDetail?> currentConversation(String agentSlug) async {
    final payload = await _apiClient.currentConversation(agentSlug);
    return payload == null ? null : _detail(payload);
  }

  Future<ConversationDetail> conversation(String conversationId) async {
    return _detail(await _apiClient.conversation(conversationId));
  }

  Future<void> startNewConversation(String agentSlug) {
    return _apiClient.startNewConversation(agentSlug);
  }

  ConversationSummary _summary(ConversationSummaryPayload payload) {
    return ConversationSummary(
      id: payload.id,
      agentSlug: payload.agentSlug,
      status: payload.status,
      title: payload.title,
      messageCount: payload.messageCount,
      createdAt: payload.createdAt,
      lastMessageAt: payload.lastMessageAt,
    );
  }

  ConversationDetail _detail(ConversationDetailPayload payload) {
    return ConversationDetail(
      conversation: _summary(payload.conversation),
      messages: [
        for (final message in payload.messages)
          Message(
            id: message.id,
            role: message.role == 'user' ? MessageRole.user : MessageRole.assistant,
            body: message.content,
            timestamp: message.createdAt,
          ),
      ],
    );
  }
}
