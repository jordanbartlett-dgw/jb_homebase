// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'conversation_state.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning

@ProviderFor(ConversationHistory)
const conversationHistoryProvider = ConversationHistoryProvider._();

final class ConversationHistoryProvider
    extends
        $AsyncNotifierProvider<ConversationHistory, List<ConversationSummary>> {
  const ConversationHistoryProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'conversationHistoryProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$conversationHistoryHash();

  @$internal
  @override
  ConversationHistory create() => ConversationHistory();
}

String _$conversationHistoryHash() =>
    r'ec585e55913bfa461ef14de88d59e4beecbdabb7';

abstract class _$ConversationHistory
    extends $AsyncNotifier<List<ConversationSummary>> {
  FutureOr<List<ConversationSummary>> build();
  @$mustCallSuper
  @override
  void runBuild() {
    final created = build();
    final ref =
        this.ref
            as $Ref<
              AsyncValue<List<ConversationSummary>>,
              List<ConversationSummary>
            >;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<
                AsyncValue<List<ConversationSummary>>,
                List<ConversationSummary>
              >,
              AsyncValue<List<ConversationSummary>>,
              Object?,
              Object?
            >;
    element.handleValue(ref, created);
  }
}

@ProviderFor(conversationDetail)
const conversationDetailProvider = ConversationDetailFamily._();

final class ConversationDetailProvider
    extends
        $FunctionalProvider<
          AsyncValue<ConversationDetail>,
          ConversationDetail,
          FutureOr<ConversationDetail>
        >
    with
        $FutureModifier<ConversationDetail>,
        $FutureProvider<ConversationDetail> {
  const ConversationDetailProvider._({
    required ConversationDetailFamily super.from,
    required String super.argument,
  }) : super(
         retry: null,
         name: r'conversationDetailProvider',
         isAutoDispose: true,
         dependencies: null,
         $allTransitiveDependencies: null,
       );

  @override
  String debugGetCreateSourceHash() => _$conversationDetailHash();

  @override
  String toString() {
    return r'conversationDetailProvider'
        ''
        '($argument)';
  }

  @$internal
  @override
  $FutureProviderElement<ConversationDetail> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<ConversationDetail> create(Ref ref) {
    final argument = this.argument as String;
    return conversationDetail(ref, argument);
  }

  @override
  bool operator ==(Object other) {
    return other is ConversationDetailProvider && other.argument == argument;
  }

  @override
  int get hashCode {
    return argument.hashCode;
  }
}

String _$conversationDetailHash() =>
    r'0766055688496c9419f36a8418ffad9245dcfee0';

final class ConversationDetailFamily extends $Family
    with $FunctionalFamilyOverride<FutureOr<ConversationDetail>, String> {
  const ConversationDetailFamily._()
    : super(
        retry: null,
        name: r'conversationDetailProvider',
        dependencies: null,
        $allTransitiveDependencies: null,
        isAutoDispose: true,
      );

  ConversationDetailProvider call(String conversationId) =>
      ConversationDetailProvider._(argument: conversationId, from: this);

  @override
  String toString() => r'conversationDetailProvider';
}
