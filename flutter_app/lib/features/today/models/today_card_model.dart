import 'package:flutter/foundation.dart';

enum TodayCardKind { morningBriefing, weeklyReview, lowRatingAlert }

@immutable
class TodayCard {
  const TodayCard({
    required this.id,
    required this.kind,
    required this.title,
    required this.body,
    required this.timestamp,
    this.subtitle,
  });

  final String id;
  final TodayCardKind kind;
  final String title;
  final String? subtitle;
  final String body;
  final DateTime timestamp;
}
