import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../shared/models/agent.dart';
import '../../shared/models/message.dart';
import '../../shared/widgets/bouncy_button.dart';
import '../../state/app_state.dart';
import '../../theme/app_theme.dart';
import 'widgets/tool_call_chip.dart';
import 'widgets/typing_indicator.dart';

/// ChatScreen — distraction-free chat with an agent picker in the header.
/// Switching agents slides the whole thread horizontally (direction
/// follows roster order) via AnimatedSwitcher keyed on agent id.
///
/// Threads live in Riverpod ([agentThreadProvider]) so they survive tab
/// switches; PR2 replaces the canned reply with gateway streaming.
class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  int _slideDirection = 1; // +1 slide from right, -1 from left
  final _input = TextEditingController();
  final _scroll = ScrollController();

  void _selectAgent(Agent agent) {
    final current = ref.read(activeAgentProvider);
    if (agent.id == current.id) return;
    final from = Agent.roster.indexWhere((a) => a.id == current.id);
    final to = Agent.roster.indexWhere((a) => a.id == agent.id);
    setState(() => _slideDirection = to > from ? 1 : -1);
    ref.read(activeAgentProvider.notifier).select(agent.id);
  }

  void _send() {
    final text = _input.text.trim();
    if (text.isEmpty) return;
    HapticFeedback.lightImpact();
    final agent = ref.read(activeAgentProvider);
    ref.read(agentThreadProvider(agent.id).notifier).appendUserMessage(text);
    _input.clear();
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scroll.hasClients) return;
      // A mid-navigation frame can attach the position before layout runs;
      // maxScrollExtent null-crashes until dimensions exist.
      if (!_scroll.position.hasContentDimensions) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOutCubic,
      );
    });
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final agent = ref.watch(activeAgentProvider);
    final messages = ref.watch(agentThreadProvider(agent.id));
    final typing = ref.watch(agentTypingProvider(agent.id));

    // Keep the newest message in view as the conversation grows.
    ref.listen(agentThreadProvider(agent.id), (previous, next) {
      if ((previous?.length ?? 0) < next.length) _scrollToEnd();
    });
    ref.listen(agentTypingProvider(agent.id), (previous, next) {
      if (next) _scrollToEnd();
    });

    return SafeArea(
      child: Column(
        children: [
          _AgentPicker(selected: agent, onSelect: _selectAgent),
          const SizedBox(height: 8),

          // Thread slides horizontally when the agent changes.
          Expanded(
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 380),
              switchInCurve: Curves.easeOutCubic,
              switchOutCurve: Curves.easeInCubic,
              transitionBuilder: (child, animation) {
                final incoming = child.key == ValueKey(agent.id);
                final begin = Offset(
                  incoming ? 0.15 * _slideDirection : -0.15 * _slideDirection,
                  0,
                );
                return FadeTransition(
                  opacity: animation,
                  child: SlideTransition(
                    position: Tween(begin: begin, end: Offset.zero).animate(animation),
                    child: child,
                  ),
                );
              },
              child: ListView.builder(
                key: ValueKey(agent.id),
                controller: _scroll,
                padding: AppTheme.pagePadding.copyWith(top: 8, bottom: 16),
                itemCount: messages.length + (typing ? 1 : 0),
                itemBuilder: (context, i) {
                  if (i == messages.length) {
                    return TypingIndicator(
                      tint: Theme.of(context).colorScheme.primary,
                    );
                  }
                  final message = messages[i];
                  if (message.role == MessageRole.toolCall) {
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 5),
                      child: ToolCallChip(message: message),
                    );
                  }
                  return _ChatBubble(message: message);
                },
              ),
            ),
          ),

          _Composer(
            controller: _input,
            onSend: _send,
            hint: agent.name,
            onMic: () => context.push(Routes.voice),
          ),
        ],
      ),
    );
  }
}

/// Horizontal agent chips. Selection is monochrome with a cobalt state dot.
class _AgentPicker extends StatelessWidget {
  const _AgentPicker({required this.selected, required this.onSelect});

  final Agent selected;
  final void Function(Agent) onSelect;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SizedBox(
      height: 44,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: AppTheme.pagePadding.copyWith(top: 4),
        itemCount: Agent.roster.length,
        separatorBuilder: (_, _) => const SizedBox(width: 10),
        itemBuilder: (context, i) {
          final agent = Agent.roster[i];
          final isSelected = agent.id == selected.id;
          final selectedInk = theme.colorScheme.onInverseSurface;
          return BouncyButton(
            onTap: () => onSelect(agent),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 250),
              curve: Curves.easeOut,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: isSelected
                    ? theme.colorScheme.inverseSurface
                    : theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(22),
                border: Border.all(
                  color: isSelected
                      ? theme.colorScheme.primary.withValues(alpha: 0.65)
                      : theme.colorScheme.outlineVariant,
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    agent.icon,
                    size: 16,
                    color: isSelected ? selectedInk : theme.colorScheme.onSurface,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    agent.name,
                    style: theme.textTheme.labelLarge?.copyWith(
                      color: isSelected ? selectedInk : theme.colorScheme.onSurface,
                    ),
                  ),
                  if (isSelected) ...[
                    const SizedBox(width: 9),
                    Container(
                      width: 6,
                      height: 6,
                      decoration: BoxDecoration(
                        color: theme.colorScheme.primary,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

/// Asymmetric-radius bubbles:
/// user   → rounded everywhere except a sharp bottom-right
/// agent  → rounded everywhere except a sharp bottom-left
class _ChatBubble extends StatelessWidget {
  const _ChatBubble({required this.message});

  final Message message;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final fromUser = message.role == MessageRole.user;
    const r = Radius.circular(AppTheme.radiusBubble);
    const sharp = Radius.circular(4);

    return Align(
      alignment: fromUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 5),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.75,
        ),
        decoration: BoxDecoration(
          color: fromUser ? theme.colorScheme.inverseSurface : theme.colorScheme.surface,
          borderRadius: BorderRadius.only(
            topLeft: r,
            topRight: r,
            bottomLeft: fromUser ? r : sharp,
            bottomRight: fromUser ? sharp : r,
          ),
          border: fromUser ? null : Border.all(color: theme.colorScheme.outlineVariant),
        ),
        child: Text(
          message.body,
          style: theme.textTheme.bodyLarge?.copyWith(
            color: fromUser ? theme.colorScheme.onInverseSurface : theme.colorScheme.onSurface,
          ),
        ),
      ),
    );
  }
}

/// Message composer pinned to the bottom: mic (voice dump), input pill,
/// send circle. The mic keeps voice reachable per the PRD.
class _Composer extends StatelessWidget {
  const _Composer({
    required this.controller,
    required this.onSend,
    required this.hint,
    required this.onMic,
  });

  final TextEditingController controller;
  final VoidCallback onSend;
  final String hint;
  final VoidCallback onMic;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: AppTheme.pagePadding.copyWith(top: 8, bottom: 12),
      child: Row(
        children: [
          BouncyButton(
            onTap: onMic,
            child: Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                color: theme.colorScheme.surface,
                shape: BoxShape.circle,
                border: Border.all(color: theme.colorScheme.outlineVariant),
              ),
              child: Icon(Icons.mic_none_rounded, color: theme.colorScheme.primary),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 18),
              decoration: BoxDecoration(
                color: theme.colorScheme.surface,
                borderRadius: BorderRadius.circular(26),
                border: Border.all(color: theme.colorScheme.outlineVariant),
              ),
              child: TextField(
                controller: controller,
                onSubmitted: (_) => onSend(),
                textInputAction: TextInputAction.send,
                style: theme.textTheme.bodyLarge,
                decoration: InputDecoration(
                  hintText: 'Message $hint',
                  hintStyle: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.outline),
                  border: InputBorder.none,
                ),
              ),
            ),
          ),
          const SizedBox(width: 10),
          BouncyButton(
            onTap: onSend,
            child: Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                color: theme.colorScheme.primary,
                shape: BoxShape.circle,
              ),
              child: Icon(Icons.arrow_upward_rounded, color: theme.colorScheme.onPrimary),
            ),
          ),
        ],
      ),
    );
  }
}
