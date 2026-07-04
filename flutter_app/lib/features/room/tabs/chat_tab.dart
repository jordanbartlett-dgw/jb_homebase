import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../shared/models/message.dart';
import '../../../shared/widgets/entrance.dart';
import '../../../shared/widgets/mic_button.dart';
import '../../../state/app_state.dart';
import '../../../theme/colors.dart';
import '../../../theme/motion.dart';
import '../../../theme/spacing.dart';
import '../widgets/chat_message.dart';
import '../widgets/tool_call_chip.dart';
import '../widgets/typing_indicator.dart';

class ChatTab extends ConsumerStatefulWidget {
  const ChatTab({super.key});

  @override
  ConsumerState<ChatTab> createState() => _ChatTabState();
}

class _ChatTabState extends ConsumerState<ChatTab> {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    // After the frame so the new item has a laid-out extent.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;
      // A mid-navigation frame can attach the position before layout runs;
      // maxScrollExtent null-crashes until dimensions exist.
      if (!_scrollController.position.hasContentDimensions) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: Motion.medium,
        curve: Motion.ease,
      );
    });
  }

  void _send() {
    final body = _controller.text.trim();
    if (body.isEmpty) return;
    HapticFeedback.lightImpact();
    ref.read(activeConversationProvider.notifier).appendUserMessage(body);
    _controller.clear();
  }

  @override
  Widget build(BuildContext context) {
    final messages = ref.watch(activeConversationProvider);
    final typing = ref.watch(assistantTypingProvider);
    final activeRoom = ref.watch(activeRoomProvider);

    // Keep the newest message in view as the conversation grows.
    ref.listen(activeConversationProvider, (previous, next) {
      if ((previous?.length ?? 0) < next.length) _scrollToBottom();
    });
    ref.listen(assistantTypingProvider, (previous, next) {
      if (next) _scrollToBottom();
    });

    return Column(
      children: [
        Expanded(
          child: ListView.separated(
            controller: _scrollController,
            padding: const EdgeInsets.fromLTRB(
              Spacing.lg,
              Spacing.lg,
              Spacing.lg,
              Spacing.md,
            ),
            itemCount: messages.length + (typing ? 1 : 0),
            separatorBuilder: (_, _) => const SizedBox(height: Spacing.md),
            itemBuilder: (context, index) {
              if (index == messages.length) {
                return const Entrance(
                  child: Padding(
                    padding: EdgeInsets.symmetric(vertical: Spacing.sm),
                    child: TypingIndicator(),
                  ),
                );
              }
              final message = messages[index];
              final child = message.role == MessageRole.toolCall
                  ? ToolCallChip(message: message)
                  : ChatMessage(message: message);
              // Only the newest message animates in. Older ones render
              // plain — a lazy list remounts items on scroll, and a
              // remounted Entrance would replay its fade-up.
              if (index != messages.length - 1) return child;
              return Entrance(key: ValueKey(message.id), child: child);
            },
          ),
        ),
        _Composer(
          controller: _controller,
          onSend: _send,
          hint: 'Message ${activeRoom.name}',
        ),
      ],
    );
  }
}

class _Composer extends StatefulWidget {
  const _Composer({
    required this.controller,
    required this.onSend,
    required this.hint,
  });

  final TextEditingController controller;
  final VoidCallback onSend;
  final String hint;

  @override
  State<_Composer> createState() => _ComposerState();
}

class _ComposerState extends State<_Composer> {
  bool _hasText = false;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onChanged);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onChanged);
    super.dispose();
  }

  void _onChanged() {
    final hasText = widget.controller.text.trim().isNotEmpty;
    if (hasText != _hasText) setState(() => _hasText = hasText);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Spacing.md,
        vertical: Spacing.sm,
      ),
      decoration: const BoxDecoration(
        color: AppColors.background,
        border: Border(top: BorderSide(color: AppColors.border, width: 0.5)),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            const Padding(
              padding: EdgeInsets.only(bottom: 2),
              child: MicButton(size: 40),
            ),
            const SizedBox(width: Spacing.sm),
            Expanded(
              child: TextField(
                controller: widget.controller,
                minLines: 1,
                maxLines: 4,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => widget.onSend(),
                decoration: InputDecoration(
                  hintText: widget.hint,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(22),
                    borderSide: const BorderSide(color: AppColors.border),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(22),
                    borderSide: const BorderSide(color: AppColors.border),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(22),
                    borderSide:
                        const BorderSide(color: AppColors.accent, width: 1.5),
                  ),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: Spacing.lg,
                    vertical: 10,
                  ),
                ),
              ),
            ),
            const SizedBox(width: Spacing.sm),
            // Send swells in once there is something to send.
            AnimatedScale(
              scale: _hasText ? 1.0 : 0.8,
              duration: Motion.fast,
              curve: Motion.ease,
              child: AnimatedOpacity(
                opacity: _hasText ? 1.0 : 0.4,
                duration: Motion.fast,
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Material(
                    color: AppColors.accent,
                    shape: const CircleBorder(),
                    child: InkWell(
                      customBorder: const CircleBorder(),
                      onTap: _hasText ? widget.onSend : null,
                      child: const SizedBox(
                        width: 40,
                        height: 40,
                        child: Icon(
                          Icons.arrow_upward,
                          color: AppColors.onAccent,
                          size: 20,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
