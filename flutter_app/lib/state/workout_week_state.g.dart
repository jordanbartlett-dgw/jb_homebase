// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'workout_week_state.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning

@ProviderFor(WorkoutWeekController)
const workoutWeekControllerProvider = WorkoutWeekControllerProvider._();

final class WorkoutWeekControllerProvider
    extends $AsyncNotifierProvider<WorkoutWeekController, WorkoutWeek> {
  const WorkoutWeekControllerProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'workoutWeekControllerProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$workoutWeekControllerHash();

  @$internal
  @override
  WorkoutWeekController create() => WorkoutWeekController();
}

String _$workoutWeekControllerHash() =>
    r'8686bba4550c408a5d40d9de7054b72b83671065';

abstract class _$WorkoutWeekController extends $AsyncNotifier<WorkoutWeek> {
  FutureOr<WorkoutWeek> build();
  @$mustCallSuper
  @override
  void runBuild() {
    final created = build();
    final ref = this.ref as $Ref<AsyncValue<WorkoutWeek>, WorkoutWeek>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<WorkoutWeek>, WorkoutWeek>,
              AsyncValue<WorkoutWeek>,
              Object?,
              Object?
            >;
    element.handleValue(ref, created);
  }
}
