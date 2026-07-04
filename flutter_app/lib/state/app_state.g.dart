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

/// Rooms — list of all rooms visible in the drawer. Hardcoded for v1.

@ProviderFor(rooms)
const roomsProvider = RoomsProvider._();

/// Rooms — list of all rooms visible in the drawer. Hardcoded for v1.

final class RoomsProvider
    extends $FunctionalProvider<List<Room>, List<Room>, List<Room>>
    with $Provider<List<Room>> {
  /// Rooms — list of all rooms visible in the drawer. Hardcoded for v1.
  const RoomsProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'roomsProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$roomsHash();

  @$internal
  @override
  $ProviderElement<List<Room>> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  List<Room> create(Ref ref) {
    return rooms(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(List<Room> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<List<Room>>(value),
    );
  }
}

String _$roomsHash() => r'3cd92fa3a2062ca353c6dc3a168287dd0f725950';

/// Currently active room. Defaults to Claw Main.
///
/// keepAlive: session state — must survive navigation between surfaces.

@ProviderFor(ActiveRoom)
const activeRoomProvider = ActiveRoomProvider._();

/// Currently active room. Defaults to Claw Main.
///
/// keepAlive: session state — must survive navigation between surfaces.
final class ActiveRoomProvider extends $NotifierProvider<ActiveRoom, Room> {
  /// Currently active room. Defaults to Claw Main.
  ///
  /// keepAlive: session state — must survive navigation between surfaces.
  const ActiveRoomProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'activeRoomProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$activeRoomHash();

  @$internal
  @override
  ActiveRoom create() => ActiveRoom();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(Room value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<Room>(value),
    );
  }
}

String _$activeRoomHash() => r'7ca704958c3de791f509eff0381783762b52f635';

/// Currently active room. Defaults to Claw Main.
///
/// keepAlive: session state — must survive navigation between surfaces.

abstract class _$ActiveRoom extends $Notifier<Room> {
  Room build();
  @$mustCallSuper
  @override
  void runBuild() {
    final created = build();
    final ref = this.ref as $Ref<Room, Room>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<Room, Room>,
              Room,
              Object?,
              Object?
            >;
    element.handleValue(ref, created);
  }
}

/// Today cards. Replace with `/api/today/cards` in PR2.

@ProviderFor(todayCards)
const todayCardsProvider = TodayCardsProvider._();

/// Today cards. Replace with `/api/today/cards` in PR2.

final class TodayCardsProvider
    extends
        $FunctionalProvider<List<TodayCard>, List<TodayCard>, List<TodayCard>>
    with $Provider<List<TodayCard>> {
  /// Today cards. Replace with `/api/today/cards` in PR2.
  const TodayCardsProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'todayCardsProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$todayCardsHash();

  @$internal
  @override
  $ProviderElement<List<TodayCard>> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  List<TodayCard> create(Ref ref) {
    return todayCards(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(List<TodayCard> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<List<TodayCard>>(value),
    );
  }
}

String _$todayCardsHash() => r'b556d16d1f2b363afefd93eb39d7a2d3aa0c6305';

/// True while the assistant is "responding". Drives the typing indicator.
///
/// keepAlive: paired with [ActiveConversation]'s pending reply timer.

@ProviderFor(AssistantTyping)
const assistantTypingProvider = AssistantTypingProvider._();

/// True while the assistant is "responding". Drives the typing indicator.
///
/// keepAlive: paired with [ActiveConversation]'s pending reply timer.
final class AssistantTypingProvider
    extends $NotifierProvider<AssistantTyping, bool> {
  /// True while the assistant is "responding". Drives the typing indicator.
  ///
  /// keepAlive: paired with [ActiveConversation]'s pending reply timer.
  const AssistantTypingProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'assistantTypingProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$assistantTypingHash();

  @$internal
  @override
  AssistantTyping create() => AssistantTyping();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(bool value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<bool>(value),
    );
  }
}

String _$assistantTypingHash() => r'6398b2278e8a993d7f28dec1097ab2441acac5af';

/// True while the assistant is "responding". Drives the typing indicator.
///
/// keepAlive: paired with [ActiveConversation]'s pending reply timer.

abstract class _$AssistantTyping extends $Notifier<bool> {
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

/// Active conversation messages for the current room.
///
/// keepAlive: switching to the Context or History tab unmounts the chat
/// tab; autoDispose would wipe the conversation (and drop any pending
/// mock reply) on every tab switch.

@ProviderFor(ActiveConversation)
const activeConversationProvider = ActiveConversationProvider._();

/// Active conversation messages for the current room.
///
/// keepAlive: switching to the Context or History tab unmounts the chat
/// tab; autoDispose would wipe the conversation (and drop any pending
/// mock reply) on every tab switch.
final class ActiveConversationProvider
    extends $NotifierProvider<ActiveConversation, List<Message>> {
  /// Active conversation messages for the current room.
  ///
  /// keepAlive: switching to the Context or History tab unmounts the chat
  /// tab; autoDispose would wipe the conversation (and drop any pending
  /// mock reply) on every tab switch.
  const ActiveConversationProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'activeConversationProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$activeConversationHash();

  @$internal
  @override
  ActiveConversation create() => ActiveConversation();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(List<Message> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<List<Message>>(value),
    );
  }
}

String _$activeConversationHash() =>
    r'de5ec261b6e1eb7acbc5cedda90a4acac71c4c51';

/// Active conversation messages for the current room.
///
/// keepAlive: switching to the Context or History tab unmounts the chat
/// tab; autoDispose would wipe the conversation (and drop any pending
/// mock reply) on every tab switch.

abstract class _$ActiveConversation extends $Notifier<List<Message>> {
  List<Message> build();
  @$mustCallSuper
  @override
  void runBuild() {
    final created = build();
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

/// Skills loaded into the active room. Read-only in v1.

@ProviderFor(roomSkills)
const roomSkillsProvider = RoomSkillsProvider._();

/// Skills loaded into the active room. Read-only in v1.

final class RoomSkillsProvider
    extends
        $FunctionalProvider<List<SkillInfo>, List<SkillInfo>, List<SkillInfo>>
    with $Provider<List<SkillInfo>> {
  /// Skills loaded into the active room. Read-only in v1.
  const RoomSkillsProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'roomSkillsProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$roomSkillsHash();

  @$internal
  @override
  $ProviderElement<List<SkillInfo>> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  List<SkillInfo> create(Ref ref) {
    return roomSkills(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(List<SkillInfo> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<List<SkillInfo>>(value),
    );
  }
}

String _$roomSkillsHash() => r'0df1547c51c2a15e37420db50f9f84f1ed25b10a';

/// History — past conversations for the active room, grouped date-wise in the UI.

@ProviderFor(roomHistory)
const roomHistoryProvider = RoomHistoryProvider._();

/// History — past conversations for the active room, grouped date-wise in the UI.

final class RoomHistoryProvider
    extends
        $FunctionalProvider<
          List<Conversation>,
          List<Conversation>,
          List<Conversation>
        >
    with $Provider<List<Conversation>> {
  /// History — past conversations for the active room, grouped date-wise in the UI.
  const RoomHistoryProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'roomHistoryProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$roomHistoryHash();

  @$internal
  @override
  $ProviderElement<List<Conversation>> $createElement(
    $ProviderPointer pointer,
  ) => $ProviderElement(pointer);

  @override
  List<Conversation> create(Ref ref) {
    return roomHistory(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(List<Conversation> value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<List<Conversation>>(value),
    );
  }
}

String _$roomHistoryHash() => r'209bdfb63378cc4d6fa2ae3c3458069abf0a18e6';
