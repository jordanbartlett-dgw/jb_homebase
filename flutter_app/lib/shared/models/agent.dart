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
    this.introduction,
    this.caution,
    this.starterPrompts = const [],
  });

  final String id;
  final String name;
  final String tagline;
  final IconData icon;

  /// A restrained cobalt-family identity color used only for small states.
  final Color tint;

  /// Optional agent-specific onboarding shown before the first message.
  final String? introduction;

  /// Important usage boundary shown without implying a positive status.
  final String? caution;

  /// Editable prompt starters for specialized agents.
  final List<String> starterPrompts;

  static const roster = <Agent>[
    Agent(
      id: 'claw-main',
      name: 'Claw Main',
      tagline: 'Anything, anytime',
      icon: Icons.auto_awesome_outlined,
      tint: Color(0xFF3157F6), // brand cobalt
    ),
    Agent(
      // Gateway slug (settings.workout_agent_slug) — NOT "workout".
      id: 'workout-coach',
      name: 'Workout Coach',
      tagline: 'Training & recovery',
      icon: Icons.directions_run_outlined,
      tint: Color(0xFF7188E8), // cobalt tint
    ),
    Agent(
      // Gateway slug — must match the agents.slug DB row exactly.
      id: 'med-check',
      name: 'Med Check',
      tagline: 'Medication screening',
      icon: Icons.medication_outlined,
      tint: Color(0xFF4A6BE0), // cobalt family, between the two existing tints
      introduction:
          'Check a medication against the current profile, public label data, '
          'QT-risk sources, and Rett-specific guidance.',
      caution:
          'Decision support, not medical clearance. Confirm medication changes '
          'with her pharmacist and cardiology team.',
      starterPrompts: [
        'Her doctor wants to start her on [medication]. Can you check it?',
        'What’s on her current medication list?',
        'She started ondansetron 4 mg as needed today. Add it to her profile.',
        'Does amoxicillin interact with anything she takes?',
      ],
    ),
  ];

  static Agent byId(String id) => roster.firstWhere((a) => a.id == id, orElse: () => roster.first);
}
