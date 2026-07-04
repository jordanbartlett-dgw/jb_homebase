import 'package:flutter/foundation.dart';

/// A Room is one agent surface. Claw Main is the only fully built room in v1.
@immutable
class Room {
  const Room({
    required this.id,
    required this.name,
    required this.icon,
    required this.subline,
    required this.isActive,
  });

  final String id;
  final String name;
  final String icon;
  final String subline;
  final bool isActive;
}
