import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../data/repositories/conversation_repository.dart';
import '../shared/api/gateway_config.dart';
import '../shared/api/mock_data.dart';
import '../shared/models/conversation.dart';
import 'core_providers.dart';

part 'conversation_state.g.dart';

final conversationRepositoryProvider = Provider<ConversationRepository>((ref) {
  return ConversationRepository(ref.watch(apiClientProvider));
});

@Riverpod(keepAlive: true)
class ConversationHistory extends _$ConversationHistory {
  String? _nextBefore;

  bool get hasMore => _nextBefore != null;

  @override
  Future<List<ConversationSummary>> build() async {
    if (!GatewayConfig.isLive) {
      _nextBefore = null;
      return MockData.conversationHistory;
    }
    final page = await ref.read(conversationRepositoryProvider).listConversations();
    _nextBefore = page.nextBefore;
    return page.conversations;
  }

  Future<void> refreshHistory() async {
    _nextBefore = null;
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => build());
  }

  Future<void> loadMore() async {
    final before = _nextBefore;
    final current = state.asData?.value;
    if (before == null || current == null) return;

    final page = await ref.read(conversationRepositoryProvider).listConversations(before: before);
    _nextBefore = page.nextBefore;
    state = AsyncData([...current, ...page.conversations]);
  }
}

@riverpod
Future<ConversationDetail> conversationDetail(
  Ref ref,
  String conversationId,
) async {
  if (!GatewayConfig.isLive) {
    return MockData.conversationDetail(conversationId);
  }
  return ref.read(conversationRepositoryProvider).conversation(conversationId);
}
