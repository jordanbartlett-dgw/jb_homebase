import 'package:flutter/material.dart';
import 'package:flutter/widget_previews.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/chat/chat_screen.dart';
import '../features/chat/widgets/agent_welcome.dart';
import '../features/home/dashboard_screen.dart';
import '../features/history/history_screen.dart';
import '../shared/models/agent.dart';
import '../theme/app_theme.dart';

/// Shared theme configuration for design review in the Flutter Widget
/// Previewer. The preview brightness control switches between both recipes.
PreviewThemeData homebasePreviewTheme() => PreviewThemeData(
  materialLight: AppTheme.light,
  materialDark: AppTheme.dark,
);

/// Supplies the Material and Riverpod context used by the app screens.
Widget homebasePreviewWrapper(Widget child) => ProviderScope(
  child: Scaffold(body: child),
);

@Preview(
  name: 'Dashboard · Light',
  group: 'Monochrome + Cobalt',
  size: Size(390, 844),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
@Preview(
  name: 'Dashboard · Dark',
  group: 'Monochrome + Cobalt',
  size: Size(390, 844),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
Widget dashboardBrandPreview() => const DashboardScreen();

@Preview(
  name: 'Agents · Light',
  group: 'Monochrome + Cobalt',
  size: Size(390, 844),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
@Preview(
  name: 'Agents · Dark',
  group: 'Monochrome + Cobalt',
  size: Size(390, 844),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
Widget agentsBrandPreview() => const ChatScreen();

@Preview(
  name: 'History · Light',
  group: 'Monochrome + Cobalt',
  size: Size(390, 844),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
@Preview(
  name: 'History · Dark',
  group: 'Monochrome + Cobalt',
  size: Size(390, 844),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
Widget historyBrandPreview() => const HistoryScreen();

void selectPreviewPrompt(String _) {}

@Preview(
  name: 'Med Check Welcome · Light',
  group: 'Med Check',
  size: Size(390, 844),
  brightness: Brightness.light,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
@Preview(
  name: 'Med Check Welcome · Dark',
  group: 'Med Check',
  size: Size(390, 844),
  brightness: Brightness.dark,
  theme: homebasePreviewTheme,
  wrapper: homebasePreviewWrapper,
)
Widget medCheckWelcomePreview() => AgentWelcome(
  agent: Agent.byId('med-check'),
  onSelectPrompt: selectPreviewPrompt,
);
