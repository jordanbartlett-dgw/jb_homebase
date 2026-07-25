// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'app_state.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// Auth state — true once the user has tapped through passkey or magic link.
///
/// keepAlive: the router only ever `ref.read`s this, so the default
/// autoDispose would drop the signed-in state the moment it was set.
///
/// Live builds boot signed in: the compile-time CLAW_APP_TOKEN is the
/// interim auth (PR2 plan), so there is nothing for a sign-in screen to do.

@ProviderFor(AuthController)
const authControllerProvider = AuthControllerProvider._();

/// Auth state — true once the user has tapped through passkey or magic link.
///
/// keepAlive: the router only ever `ref.read`s this, so the default
/// autoDispose would drop the signed-in state the moment it was set.
///
/// Live builds boot signed in: the compile-time CLAW_APP_TOKEN is the
/// interim auth (PR2 plan), so there is nothing for a sign-in screen to do.
final class AuthControllerProvider
    extends $NotifierProvider<AuthController, bool> {
  /// Auth state — true once the user has tapped through passkey or magic link.
  ///
  /// keepAlive: the router only ever `ref.read`s this, so the default
  /// autoDispose would drop the signed-in state the moment it was set.
  ///
  /// Live builds boot signed in: the compile-time CLAW_APP_TOKEN is the
  /// interim auth (PR2 plan), so there is nothing for a sign-in screen to do.
  const AuthControllerProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'authControllerProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$authControllerHash();

  @$internal
  @override
  AuthController create() => AuthController();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(bool value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<bool>(value),
    );
  }
}

String _$authControllerHash() => r'64738a93e99b8d35ab14286d9a8fb7e40ecf3aac';

/// Auth state — true once the user has tapped through passkey or magic link.
///
/// keepAlive: the router only ever `ref.read`s this, so the default
/// autoDispose would drop the signed-in state the moment it was set.
///
/// Live builds boot signed in: the compile-time CLAW_APP_TOKEN is the
/// interim auth (PR2 plan), so there is nothing for a sign-in screen to do.

abstract class _$AuthController extends $Notifier<bool> {
  bool build();
  @$mustCallSuper
  @override
  void runBuild() {
    final created = build();
    final ref = this.ref as $Ref<bool, bool>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<bool, bool>,
              bool,
              Object?,
              Object?
            >;
    element.handleValue(ref, created);
  }
}

/// Currently selected agent in the chat surface. The dashboard dock and
/// the in-chat agent picker both drive this.
///
/// keepAlive: session state — must survive navigation between tabs.

@ProviderFor(ActiveAgent)
const activeAgentProvider = ActiveAgentProvider._();

/// Currently selected agent in the chat surface. The dashboard dock and
/// the in-chat agent picker both drive this.
///
/// keepAlive: session state — must survive navigation between tabs.
final class ActiveAgentProvider extends $NotifierProvider<ActiveAgent, Agent> {
  /// Currently selected agent in the chat surface. The dashboard dock and
  /// the in-chat agent picker both drive this.
  ///
  /// keepAlive: session state — must survive navigation between tabs.
  const ActiveAgentProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'activeAgentProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$activeAgentHash();

  @$internal
  @override
  ActiveAgent create() => ActiveAgent();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(Agent value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<Agent>(value),
    );
  }
}

String _$activeAgentHash() => r'2b8ce0bd248e29f5703dde40f0cfb5b48ffc5ede';

/// Currently selected agent in the chat surface. The dashboard dock and
/// the in-chat agent picker both drive this.
///
/// keepAlive: session state — must survive navigation between tabs.

abstract class _$ActiveAgent extends $Notifier<Agent> {
  Agent build();
  @$mustCallSuper
  @override
  void runBuild() {
    final created = build();
    final ref = this.ref as $Ref<Agent, Agent>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<Agent, Agent>,
              Agent,
              Object?,
              Object?
            >;
    element.handleValue(ref, created);
  }
}

/// True while an agent is "responding". Drives its typing indicator.
///
/// keepAlive: paired with [AgentThread]'s pending reply timer.

@ProviderFor(AgentTyping)
const agentTypingProvider = AgentTypingFamily._();

/// True while an agent is "responding". Drives its typing indicator.
///
/// keepAlive: paired with [AgentThread]'s pending reply timer.
final class AgentTypingProvider extends $NotifierProvider<AgentTyping, bool> {
  /// True while an agent is "responding". Drives its typing indicator.
  ///
  /// keepAlive: paired with [AgentThread]'s pending reply timer.
  const AgentTypingProvider._({
    required AgentTypingFamily super.from,
    required String super.argument,
  }) : super(
         retry: null,
         name: r'agentTypingProvider',
         isAutoDispose: false,
         dependencies: null,
         $allTransitiveDependencies: null,
       );

  @override
  String debugGetCreateSourceHash() => _$agentTypingHash();

  @override
  String toString() {
    return r'agentTypingProvider'
        ''
        '($argument)';
  }

  @$internal
  @override
  AgentTyping create() => AgentTyping();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(bool value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<bool>(value),
    );
  }

  @override
  bool operator ==(Object other) {
    return other is AgentTypingProvider && other.argument == argument;
  }

  @override
  int get hashCode {
    return argument.hashCode;
  }
}

String _$agentTypingHash() => r'df48f2771568fa67490641c87fb77e93cd4f3d7a';

/// True while an agent is "responding". Drives its typing indicator.
///
/// keepAlive: paired with [AgentThread]'s pending reply timer.

final class AgentTypingFamily extends $Family
    with $ClassFamilyOverride<AgentTyping, bool, bool, bool, String> {
  const AgentTypingFamily._()
    : super(
        retry: null,
        name: r'agentTypingProvider',
        dependencies: null,
        $allTransitiveDependencies: null,
        isAutoDispose: false,
      );

  /// True while an agent is "responding". Drives its typing indicator.
  ///
  /// keepAlive: paired with [AgentThread]'s pending reply timer.

  AgentTypingProvider call(String agentId) =>
      AgentTypingProvider._(argument: agentId, from: this);

  @override
  String toString() => r'agentTypingProvider';
}

/// True while an agent is "responding". Drives its typing indicator.
///
/// keepAlive: paired with [AgentThread]'s pending reply timer.

abstract class _$AgentTyping extends $Notifier<bool> {
  late final _$args = ref.$arg as String;
  String get agentId => _$args;

  bool build(String agentId);
  @$mustCallSuper
  @override
  void runBuild() {
    final created = build(_$args);
    final ref = this.ref as $Ref<bool, bool>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<bool, bool>,
              bool,
              Object?,
              Object?
            >;
    element.handleValue(ref, created);
  }
}

/// Chat thread per agent. Threads live for the whole session so switching
/// agents (or tabs) never wipes a conversation.

@ProviderFor(AgentThread)
const agentThreadProvider = AgentThreadFamily._();

/// Chat thread per agent. Threads live for the whole session so switching
/// agents (or tabs) never wipes a conversation.
final class AgentThreadProvider
    extends $AsyncNotifierProvider<AgentThread, List<Message>> {
  /// Chat thread per agent. Threads live for the whole session so switching
  /// agents (or tabs) never wipes a conversation.
  const AgentThreadProvider._({
    required AgentThreadFamily super.from,
    required String super.argument,
  }) : super(
         retry: null,
         name: r'agentThreadProvider',
         isAutoDispose: false,
         dependencies: null,
         $allTransitiveDependencies: null,
       );

  @override
  String debugGetCreateSourceHash() => _$agentThreadHash();

  @override
  String toString() {
    return r'agentThreadProvider'
        ''
        '($argument)';
  }

  @$internal
  @override
  AgentThread create() => AgentThread();

  @override
  bool operator ==(Object other) {
    return other is AgentThreadProvider && other.argument == argument;
  }

  @override
  int get hashCode {
    return argument.hashCode;
  }
}

String _$agentThreadHash() => r'1b050d48634ad55eb415a3c887b322a58828fab5';

/// Chat thread per agent. Threads live for the whole session so switching
/// agents (or tabs) never wipes a conversation.

final class AgentThreadFamily extends $Family
    with
        $ClassFamilyOverride<
          AgentThread,
          AsyncValue<List<Message>>,
          List<Message>,
          FutureOr<List<Message>>,
          String
        > {
  const AgentThreadFamily._()
    : super(
        retry: null,
        name: r'agentThreadProvider',
        dependencies: null,
        $allTransitiveDependencies: null,
        isAutoDispose: false,
      );

  /// Chat thread per agent. Threads live for the whole session so switching
  /// agents (or tabs) never wipes a conversation.

  AgentThreadProvider call(String agentId) =>
      AgentThreadProvider._(argument: agentId, from: this);

  @override
  String toString() => r'agentThreadProvider';
}

/// Chat thread per agent. Threads live for the whole session so switching
/// agents (or tabs) never wipes a conversation.

abstract class _$AgentThread extends $AsyncNotifier<List<Message>> {
  late final _$args = ref.$arg as String;
  String get agentId => _$args;

  FutureOr<List<Message>> build(String agentId);
  @$mustCallSuper
  @override
  void runBuild() {
    final created = build(_$args);
    final ref = this.ref as $Ref<AsyncValue<List<Message>>, List<Message>>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<List<Message>>, List<Message>>,
              AsyncValue<List<Message>>,
              Object?,
              Object?
            >;
    element.handleValue(ref, created);
  }
}
