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

@ProviderFor(AuthController)
const authControllerProvider = AuthControllerProvider._();

/// Auth state — true once the user has tapped through passkey or magic link.
///
/// keepAlive: the router only ever `ref.read`s this, so the default
/// autoDispose would drop the signed-in state the moment it was set.
final class AuthControllerProvider
    extends $NotifierProvider<AuthController, bool> {
  /// Auth state — true once the user has tapped through passkey or magic link.
  ///
  /// keepAlive: the router only ever `ref.read`s this, so the default
  /// autoDispose would drop the signed-in state the moment it was set.
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

String _$authControllerHash() => r'9bdc1f377ccabdc8d37330349bdf97becc020cab';

/// Auth state — true once the user has tapped through passkey or magic link.
///
/// keepAlive: the router only ever `ref.read`s this, so the default
/// autoDispose would drop the signed-in state the moment it was set.

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
    extends $NotifierProvider<AgentThread, List<Message>> {
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

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(List<Message> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<List<Message>>(value),
    );
  }

  @override
  bool operator ==(Object other) {
    return other is AgentThreadProvider && other.argument == argument;
  }

  @override
  int get hashCode {
    return argument.hashCode;
  }
}

String _$agentThreadHash() => r'38ddddfff53e5cb8859fd419521d5226c99f0ab1';

/// Chat thread per agent. Threads live for the whole session so switching
/// agents (or tabs) never wipes a conversation.

final class AgentThreadFamily extends $Family
    with
        $ClassFamilyOverride<
          AgentThread,
          List<Message>,
          List<Message>,
          List<Message>,
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

abstract class _$AgentThread extends $Notifier<List<Message>> {
  late final _$args = ref.$arg as String;
  String get agentId => _$args;

  List<Message> build(String agentId);
  @$mustCallSuper
  @override
  void runBuild() {
    final created = build(_$args);
    final ref = this.ref as $Ref<List<Message>, List<Message>>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<List<Message>, List<Message>>,
              List<Message>,
              Object?,
              Object?
            >;
    element.handleValue(ref, created);
  }
}
