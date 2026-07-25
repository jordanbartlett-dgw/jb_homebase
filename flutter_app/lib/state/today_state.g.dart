// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'today_state.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning

@ProviderFor(TodayController)
const todayControllerProvider = TodayControllerProvider._();

final class TodayControllerProvider
    extends $AsyncNotifierProvider<TodayController, TodayOverview> {
  const TodayControllerProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'todayControllerProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$todayControllerHash();

  @$internal
  @override
  TodayController create() => TodayController();
}

String _$todayControllerHash() => r'b9621935ec49c51e53d2d78d0ba9580a535be9cc';

abstract class _$TodayController extends $AsyncNotifier<TodayOverview> {
  FutureOr<TodayOverview> build();
  @$mustCallSuper
  @override
  void runBuild() {
    final created = build();
    final ref = this.ref as $Ref<AsyncValue<TodayOverview>, TodayOverview>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<TodayOverview>, TodayOverview>,
              AsyncValue<TodayOverview>,
              Object?,
              Object?
            >;
    element.handleValue(ref, created);
  }
}
