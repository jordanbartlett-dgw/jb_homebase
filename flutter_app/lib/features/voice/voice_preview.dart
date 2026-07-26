import 'dart:async';
import 'dart:io';

import 'package:audio_waveforms/audio_waveforms.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../routing/routes.dart';
import '../../shared/models/agent.dart';
import '../../state/app_state.dart';
import '../../theme/spacing.dart';
import 'voice_draft.dart';
import 'voice_providers.dart';

/// Transcript and audio review. Nothing reaches an agent until Send is tapped.
class VoicePreview extends ConsumerStatefulWidget {
  const VoicePreview({
    super.key,
    required this.draft,
    this.enableAudioPlayback = true,
  });

  final VoiceDraft draft;

  /// Disabled by widget previews/tests where native media channels are absent.
  final bool enableAudioPlayback;

  @override
  ConsumerState<VoicePreview> createState() => _VoicePreviewState();
}

class _VoicePreviewState extends ConsumerState<VoicePreview> {
  late final TextEditingController _transcriptController;
  PlayerController? _player;
  StreamSubscription<PlayerState>? _playerSubscription;
  StreamSubscription<void>? _completionSubscription;

  bool _audioReady = false;
  bool _playing = false;
  bool _sending = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _transcriptController = TextEditingController(text: widget.draft.transcript);
    if (widget.enableAudioPlayback) unawaited(_preparePlayer());
  }

  Future<void> _preparePlayer() async {
    final player = PlayerController()..updateFrequency = UpdateFrequency.high;
    _player = player;
    try {
      await player.preparePlayer(path: widget.draft.audioPath, noOfSamples: 56);
      if (!mounted) return;
      _playerSubscription = player.onPlayerStateChanged.listen((state) {
        if (mounted) setState(() => _playing = state == PlayerState.playing);
      });
      _completionSubscription = player.onCompletion.listen((_) {
        if (mounted) setState(() => _playing = false);
      });
      setState(() => _audioReady = true);
    } on Exception {
      // Transcript review/send remains usable if native playback preparation
      // fails. The retained file can still be discarded or re-recorded.
      if (mounted) setState(() => _audioReady = false);
    }
  }

  Future<void> _togglePlayback() async {
    final player = _player;
    if (!_audioReady || player == null) return;
    if (_playing) {
      await player.pausePlayer();
    } else {
      await player.startPlayer();
    }
  }

  Future<void> _discardAndClose() async {
    await _deleteAudio();
    if (mounted) context.pop();
  }

  Future<void> _reRecord() async {
    await _deleteAudio();
    if (!mounted) return;
    context.pushReplacement(Routes.voice);
  }

  Future<void> _send() async {
    final transcript = _transcriptController.text.trim();
    if (transcript.isEmpty || _sending) return;
    FocusManager.instance.primaryFocus?.unfocus();
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      final response = await ref
          .read(voiceServiceProvider)
          .send(draft: widget.draft, transcript: transcript);
      final routedAgent = Agent.byId(response.agentSlug);
      await ref.read(agentThreadProvider(routedAgent.id).future);
      ref
          .read(agentThreadProvider(routedAgent.id).notifier)
          .appendVoiceExchange(transcript: transcript, reply: response.reply);
      ref.read(activeAgentProvider.notifier).select(routedAgent.id);
      unawaited(_deleteAudio());
      if (mounted) context.go(Routes.agents);
    } on Exception catch (error) {
      debugPrint('Voice send failed: $error');
      if (mounted) {
        setState(() {
          _sending = false;
          _error = 'Couldn’t send that voice dump. Your draft is still here.';
        });
      }
    }
  }

  Future<void> _deleteAudio() async {
    final file = File(widget.draft.audioPath);
    if (await file.exists()) {
      try {
        await file.delete();
      } on FileSystemException {
        // Temporary files are also cleared by the operating system.
      }
    }
  }

  @override
  void dispose() {
    _transcriptController.dispose();
    unawaited(_playerSubscription?.cancel());
    unawaited(_completionSubscription?.cancel());
    _player?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final textTheme = theme.textTheme;

    return Scaffold(
      appBar: AppBar(
        title: Text('Voice preview', style: textTheme.titleMedium),
        leading: IconButton(
          icon: const Icon(Icons.close),
          onPressed: _sending ? null : _discardAndClose,
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            Spacing.lg,
            Spacing.md,
            Spacing.lg,
            Spacing.lg,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('TRANSCRIPT', style: textTheme.labelSmall),
              const SizedBox(height: Spacing.sm),
              TextField(
                key: const ValueKey('voice-transcript'),
                controller: _transcriptController,
                enabled: !_sending,
                minLines: 5,
                maxLines: 10,
                textCapitalization: TextCapitalization.sentences,
                decoration: const InputDecoration(
                  hintText: 'Your transcript will appear here.',
                  alignLabelWithHint: true,
                ),
              ),
              const SizedBox(height: Spacing.xl),
              Text('AUDIO', style: textTheme.labelSmall),
              const SizedBox(height: Spacing.sm),
              _AudioScrubber(
                player: _player,
                ready: _audioReady,
                playing: _playing,
                duration: widget.draft.duration,
                onToggle: _togglePlayback,
              ),
              if (_error != null) ...[
                const SizedBox(height: Spacing.md),
                Text(
                  _error!,
                  style: textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
                ),
              ],
              const Spacer(),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: _sending ? null : _discardAndClose,
                      child: const Text('Discard'),
                    ),
                  ),
                  const SizedBox(width: Spacing.sm),
                  Expanded(
                    child: OutlinedButton(
                      onPressed: _sending ? null : _reRecord,
                      child: const Text('Re-record'),
                    ),
                  ),
                  const SizedBox(width: Spacing.sm),
                  Expanded(
                    child: FilledButton(
                      onPressed: _sending ? null : _send,
                      child: _sending
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Send'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AudioScrubber extends StatelessWidget {
  const _AudioScrubber({
    required this.player,
    required this.ready,
    required this.playing,
    required this.duration,
    required this.onToggle,
  });

  final PlayerController? player;
  final bool ready;
  final bool playing;
  final Duration duration;
  final VoidCallback onToggle;

  String get durationLabel {
    final minutes = duration.inMinutes;
    final seconds = (duration.inSeconds % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      height: 76,
      padding: const EdgeInsets.symmetric(horizontal: Spacing.sm),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Row(
        children: [
          IconButton(
            tooltip: playing ? 'Pause recording' : 'Play recording',
            onPressed: ready ? onToggle : null,
            icon: Icon(playing ? Icons.pause_rounded : Icons.play_arrow_rounded),
            color: theme.colorScheme.primary,
          ),
          Expanded(
            child: ready && player != null
                ? LayoutBuilder(
                    builder: (context, constraints) => AudioFileWaveforms(
                      size: Size(constraints.maxWidth, 52),
                      playerController: player!,
                      playerWaveStyle: PlayerWaveStyle(
                        fixedWaveColor: theme.colorScheme.outlineVariant,
                        liveWaveColor: theme.colorScheme.primary,
                        backgroundColor: Colors.transparent,
                        showSeekLine: false,
                        spacing: 5,
                        waveThickness: 3,
                      ),
                    ),
                  )
                : _StaticWaveform(color: theme.colorScheme.outlineVariant),
          ),
          const SizedBox(width: Spacing.sm),
          Text(durationLabel, style: theme.textTheme.bodySmall),
        ],
      ),
    );
  }
}

class _StaticWaveform extends StatelessWidget {
  const _StaticWaveform({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    const heights = <double>[8, 18, 28, 14, 35, 24, 12, 31, 20, 9, 26, 16];
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: [
        for (final height in heights)
          Container(
            width: 3,
            height: height,
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
      ],
    );
  }
}
