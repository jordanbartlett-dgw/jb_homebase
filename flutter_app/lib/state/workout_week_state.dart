import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../data/repositories/workout_week_repository.dart';
import '../shared/api/gateway_config.dart';
import '../shared/api/mock_data.dart';
import '../shared/models/workout_week.dart';
import 'core_providers.dart';

part 'workout_week_state.g.dart';

final workoutWeekRepositoryProvider = Provider<WorkoutWeekRepository>((ref) {
  return WorkoutWeekRepository(ref.watch(apiClientProvider));
});

@Riverpod(keepAlive: true)
class WorkoutWeekController extends _$WorkoutWeekController {
  @override
  Future<WorkoutWeek> build() async {
    if (!GatewayConfig.isLive) return MockData.workoutWeek;
    return ref.read(workoutWeekRepositoryProvider).fetchWeek();
  }

  Future<void> refreshWeek() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(build);
  }
}
