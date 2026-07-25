import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../data/repositories/today_repository.dart';
import '../shared/api/gateway_config.dart';
import '../shared/api/mock_data.dart';
import '../shared/models/today.dart';
import 'core_providers.dart';

part 'today_state.g.dart';

final todayRepositoryProvider = Provider<TodayRepository>((ref) {
  return TodayRepository(ref.watch(apiClientProvider));
});

@Riverpod(keepAlive: true)
class TodayController extends _$TodayController {
  @override
  Future<TodayOverview> build() async {
    if (!GatewayConfig.isLive) return MockData.todayOverview;
    return ref.read(todayRepositoryProvider).fetchToday();
  }

  Future<void> refreshToday() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(build);
  }
}
