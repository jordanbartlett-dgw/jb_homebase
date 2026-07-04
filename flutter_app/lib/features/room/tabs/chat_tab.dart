import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/message.dart';
import '../../../state/app_state.dart';
import '../../../theme/colors.dart';
import '../../../theme/spacing.dart';
import '../widgets/chat_message.dart';
import '../widgets/tool_call_chip.dart';

class ChatTab extends ConsumerStatefulWidget {
  const ChatTab({super.key});

  @override
  ConsumerState<ChatTab> createState() => _ChatTabState();
}

class _ChatTabState extends ConsumerState<ChatTab> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _send() {
    final body = _controller.text.trim();
    if (body.isEmpty) return;
    ref.read(activeConversationProvider.notifier).appendUserMessage(body);
    _controller.clear();
    // TODO(backend): stream assistant response from gateway.
  }

  @override
  Widget build(BuildContext context) {
    final messages = ref.watch(activeConversationProvider);

    return Column(
      children: [
        Expanded(
          child: ListView.separated(
            padding: const EdgeInsets.fromLTRB(
              Spacing.lg,
              Spacing.lg,
              Spacing.lg,
              Spacing.md,
            ),
            itemCount: messages.length,
            separatorBuilder: (_, _) => const SizedBox(height: Spacing.md),
            itemBuilder: (context, index) {
              final message = messages[index];
              if (message.role == MessageRole.toolCall) {
                return ToolCallChip(message: message);
              }
              return ChatMessage(message: message);
            },
          ),
        ),
        _Composer(controller: _controller, onSend: _send),
      ],
    );
  }
}

class _Composer extends StatelessWidget {
  const _Composer({required this.controller, required this.onSend});

  final TextEditingController controller;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Spacing.lg,
        vertical: Spacing.sm,
      ),
      decoration: const BoxDecoration(
        color: AppColors.background,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: controller,
                minLines: 1,
                maxLines: 4,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => onSend(),
                decoration: const InputDecoration(hintText: 'Message Claw Main'),
              ),
            ),
            const SizedBox(width: Spacing.sm),
            IconButton(
              onPressed: onSend,
              icon: const Icon(Icons.send, color: AppColors.accent),
              tooltip: 'Send',
            ),
          ],
        ),
      ),
    );
  }
}
