import 'package:flutter/foundation.dart';

/// A skill loaded into a room. Read-only in v1; editing scope is v1.1.
@immutable
class SkillInfo {
  const SkillInfo({required this.name, required this.description});

  final String name;
  final String description;
}
