import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';

/// Minimal workout-analytics placeholder: a smooth cubic sparkline with a
/// soft gradient fill, drawn with a CustomPainter. The line animates in
/// (progressive draw) on first build. Feed it real data later via [values].
class SparklineCard extends StatelessWidget {
  const SparklineCard({
    super.key,
    this.title = 'Training load',
    this.caption = 'Last 14 sessions',
    this.values = const [3, 4, 3.5, 5, 4.5, 6, 5.5, 7, 6.5, 6, 7.5, 7, 8, 8.5],
  });

  final String title;
  final String caption;
  final List<double> values;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(AppTheme.radiusCard),
        boxShadow: AppTheme.softShadow(context),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title.toUpperCase(), style: theme.textTheme.titleSmall),
          const SizedBox(height: 4),
          Text(caption, style: theme.textTheme.bodySmall),
          const SizedBox(height: 16),
          SizedBox(
            height: 90,
            width: double.infinity,
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: 1),
              duration: const Duration(milliseconds: 1200),
              curve: Curves.easeOutCubic,
              builder: (context, progress, _) => CustomPaint(
                painter: _SparklinePainter(
                  values: values,
                  progress: progress,
                  lineColor: theme.colorScheme.primary,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SparklinePainter extends CustomPainter {
  _SparklinePainter({
    required this.values,
    required this.progress,
    required this.lineColor,
  });

  final List<double> values;
  final double progress; // 0..1 draw progress
  final Color lineColor;

  @override
  void paint(Canvas canvas, Size size) {
    if (values.length < 2) return;

    final min = values.reduce(math.min);
    final max = values.reduce(math.max);
    final range = (max - min) == 0 ? 1 : (max - min);

    Offset point(int i) => Offset(
          size.width * i / (values.length - 1),
          // 10% vertical padding top and bottom
          size.height * (0.9 - 0.8 * (values[i] - min) / range),
        );

    // Smooth path via midpoint quadratic beziers.
    final path = Path()..moveTo(point(0).dx, point(0).dy);
    for (var i = 0; i < values.length - 1; i++) {
      final p0 = point(i);
      final p1 = point(i + 1);
      final mid = Offset((p0.dx + p1.dx) / 2, (p0.dy + p1.dy) / 2);
      path.quadraticBezierTo(p0.dx, p0.dy, mid.dx, mid.dy);
    }
    path.lineTo(point(values.length - 1).dx, point(values.length - 1).dy);

    // Progressive draw: extract the first [progress] fraction of the path.
    final metrics = path.computeMetrics().first;
    final drawn = metrics.extractPath(0, metrics.length * progress);

    // Gradient fill under the drawn portion.
    final fill = Path.from(drawn)
      ..lineTo(size.width * progress, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(
      fill,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            lineColor.withValues(alpha: 0.22),
            lineColor.withValues(alpha: 0),
          ],
        ).createShader(Offset.zero & size),
    );

    canvas.drawPath(
      drawn,
      Paint()
        ..color = lineColor
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5
        ..strokeCap = StrokeCap.round,
    );

    // Endpoint dot once fully drawn.
    if (progress == 1) {
      canvas.drawCircle(point(values.length - 1), 4, Paint()..color = lineColor);
    }
  }

  @override
  bool shouldRepaint(_SparklinePainter old) =>
      old.progress != progress || old.values != values;
}
