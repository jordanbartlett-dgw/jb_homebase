import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'routing/app_router.dart';
import 'theme/app_theme.dart';

class JordanClawApp extends ConsumerWidget {
  const JordanClawApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = buildAppRouter(ref);

    return MaterialApp.router(
      title: 'Jordan Claw',
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.light,
      routerConfig: router,
      debugShowCheckedModeBanner: false,
    );
  }
}
