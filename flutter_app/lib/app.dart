import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'routing/app_router.dart';
import 'theme/app_theme.dart';

/// JB Homebase — command center for Jordan Claw agents.
class JBHomebaseApp extends ConsumerWidget {
  const JBHomebaseApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = buildAppRouter(ref);

    return MaterialApp.router(
      title: 'JB Homebase',
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.system,
      routerConfig: router,
      debugShowCheckedModeBanner: false,
    );
  }
}
