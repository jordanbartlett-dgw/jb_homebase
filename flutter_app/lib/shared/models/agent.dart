import 'package:flutter/material.dart';

/// Adding an agent to Homebase = adding one entry to [Agent.roster].
/// Later this loads from the Jordan Claw gateway; the UI never needs to
/// change. Keep IDs stable — they key chat threads and (later) backend
/// routing to the gateway's agent slugs.
class Agent {
  const Agent({
    required this.id,
    required this.name,
    required this.tagline,
    required this.icon,
    required this.tint,
  });

  final String id;
  final String name;
  final String tagline;
  final IconData icon;

  /// Per-agent identity color, blended over surface at low alpha so dock
  /// cards stay within the palette.
  final Color tint;

  static const roster = <Agent>[
    Agent(
      id: 'claw-main',
      name: 'Claw Main',
      tagline: 'Anything, anytime',
      icon: Icons.auto_awesome_outlined,
      tint: Color(0xFF64805F), // sage
    ),
    Agent(
      id: 'workout',
      name: 'Workout Coach',
      tagline: 'Training & recovery',
      icon: Icons.directions_run_outlined,
      tint: Color(0xFF6E7F98), // slate-blue
    ),
  ];

  static Agent byId(String id) =>
      roster.firstWhere((a) => a.id == id, orElse: () => roster.first);
}
