import '../models/conversation.dart';
import '../models/message.dart';
import '../models/today.dart';
import '../models/workout_week.dart';

/// All mock data for the design build. Replace with real API calls in PR2.
///
/// Times are computed relative to a reference moment so the UI looks
/// reasonable on any launch day. Real timestamps come from the server.
class MockData {
  const MockData._();

  static DateTime get _now => DateTime(2026, 7, 4, 8, 15);

  static TodayOverview get todayOverview {
    final now = DateTime.now();
    final day = DateTime(now.year, now.month, now.day);
    return TodayOverview(
      date: day,
      timezone: 'America/Chicago',
      digest: DailyDigest(
        id: 'digest-today',
        content:
            'Your board call is at 10:00 AM. Review the open SAGE quotes '
            'beforehand, and protect the afternoon focus block.',
        generatedAt: day.add(const Duration(hours: 7, minutes: 2)),
      ),
      calendarAvailable: true,
      calendarMessage: null,
      artifacts: [
        ProactiveArtifact(
          taskType: 'memory_flag',
          content:
              'I updated my understanding:\n'
              'Before: The vendor lead time is 48 hours.\n'
              'Now: The vendor committed to a 36-hour lead time.\n\n'
              'Let me know if that’s wrong.',
          createdAt: day.add(const Duration(hours: 8, minutes: 4)),
        ),
        ProactiveArtifact(
          taskType: 'event_trigger',
          content:
              '**Agent inbox update**\n\n'
              'A vendor replied about quote 4438. They can meet the requested '
              'lead time if artwork is approved before noon.',
          createdAt: day.add(const Duration(hours: 7, minutes: 48)),
        ),
        ProactiveArtifact(
          taskType: 'care_docs_check',
          content:
              'The caregiver handoff is out of date because care details '
              'changed. Ask Med Check to regenerate it.',
          createdAt: day.subtract(const Duration(hours: 10)),
        ),
        ProactiveArtifact(
          taskType: 'weekly_training_review',
          content:
              'You completed three planned sessions this week. Keep Monday '
              'easy after the hill work and protect the Wednesday recovery day.',
          createdAt: day.subtract(const Duration(days: 1, hours: 2)),
        ),
      ],
      events: [
        CalendarEvent(
          id: 'event-board-call',
          title: 'FG board call',
          startsAt: day.add(const Duration(hours: 10)),
          endsAt: day.add(const Duration(hours: 11)),
          allDay: false,
          location: 'Zoom',
        ),
        CalendarEvent(
          id: 'event-focus',
          title: 'Focus block',
          startsAt: day.add(const Duration(hours: 13)),
          endsAt: day.add(const Duration(hours: 15)),
          allDay: false,
          location: null,
        ),
        CalendarEvent(
          id: 'event-family',
          title: 'Family day',
          startsAt: day.add(const Duration(days: 1)),
          endsAt: day.add(const Duration(days: 2)),
          allDay: true,
          location: null,
        ),
      ],
    );
  }

  // ---------------------------------------------------------------------------
  // Chat threads, keyed by agent id.
  // ---------------------------------------------------------------------------

  static List<Message> threadFor(String agentId) => switch (agentId) {
    'workout-coach' => [
      Message(
        id: 'workout-1',
        role: MessageRole.assistant,
        body:
            'Hill repeats today: 6 x 90s at the neighborhood hill. '
            'Ready when you are.',
        timestamp: _now.subtract(const Duration(minutes: 40)),
      ),
    ],
    'med-check' => [
      Message(
        id: 'med-check-1',
        role: MessageRole.assistant,
        body:
            'I can screen a medication against the current profile and public '
            'sources. I’ll report what I find, but the pharmacist and cardiology '
            'team should confirm every medication change.',
        timestamp: _now.subtract(const Duration(minutes: 30)),
      ),
    ],
    _ => [
      Message(
        id: 'main-1',
        role: MessageRole.user,
        body: 'What is on my plate before the FG board call?',
        timestamp: _now.subtract(const Duration(minutes: 20)),
      ),
      Message(
        id: 'main-2',
        role: MessageRole.assistant,
        body:
            'Two quotes in SAGE that need follow-up by noon, and the '
            'FG board agenda review. I can pull both up.',
        timestamp: _now.subtract(const Duration(minutes: 19, seconds: 30)),
      ),
      Message(
        id: 'main-3',
        role: MessageRole.user,
        body: 'Pull the SAGE quotes.',
        timestamp: _now.subtract(const Duration(minutes: 18)),
      ),
      Message(
        id: 'main-4',
        role: MessageRole.toolCall,
        body: '',
        timestamp: _now.subtract(const Duration(minutes: 17, seconds: 45)),
        toolName: 'sage_connect.search_quotes',
        toolStatus: ToolCallStatus.success,
        toolDetail: 'Searched SAGE — 2 open quotes found',
      ),
      Message(
        id: 'main-5',
        role: MessageRole.assistant,
        body:
            'Found two open quotes. Quote 4421 is waiting on artwork '
            'approval from the client. Quote 4438 needs a vendor '
            'response on lead time. Want the contact details for both?',
        timestamp: _now.subtract(const Duration(minutes: 17)),
      ),
    ],
  };

  static List<ConversationSummary> get conversationHistory => [
    ConversationSummary(
      id: 'history-main-today',
      agentSlug: 'claw-main',
      status: 'active',
      title: 'What is on my plate before the FG board call?',
      messageCount: 5,
      createdAt: _now.subtract(const Duration(minutes: 20)),
      lastMessageAt: _now.subtract(const Duration(minutes: 17)),
    ),
    ConversationSummary(
      id: 'history-med-check-today',
      agentSlug: 'med-check',
      status: 'archived',
      title: 'Check ondansetron against her current medication list',
      messageCount: 2,
      createdAt: _now.subtract(const Duration(hours: 3)),
      lastMessageAt: _now.subtract(const Duration(hours: 2, minutes: 58)),
    ),
    ConversationSummary(
      id: 'history-workout-yesterday',
      agentSlug: 'workout-coach',
      status: 'archived',
      title: 'Adjust this week after the hill session',
      messageCount: 2,
      createdAt: _now.subtract(const Duration(days: 1, hours: 2)),
      lastMessageAt: _now.subtract(const Duration(days: 1, hours: 1)),
    ),
    ConversationSummary(
      id: 'history-main-older',
      agentSlug: 'claw-main',
      status: 'archived',
      title: 'Summarize the open SAGE quotes',
      messageCount: 2,
      createdAt: _now.subtract(const Duration(days: 10)),
      lastMessageAt: _now.subtract(const Duration(days: 10)),
    ),
  ];

  static ConversationDetail conversationDetail(String conversationId) {
    final summary = conversationHistory.firstWhere(
      (conversation) => conversation.id == conversationId,
      orElse: () => conversationHistory.first,
    );
    return ConversationDetail(
      conversation: summary,
      messages: summary.id == 'history-main-today'
          ? threadFor('claw-main').where((message) {
              return message.role != MessageRole.toolCall;
            }).toList()
          : [
              Message(
                id: '${summary.id}-user',
                role: MessageRole.user,
                body: summary.title,
                timestamp: summary.createdAt,
              ),
              Message(
                id: '${summary.id}-assistant',
                role: MessageRole.assistant,
                body: summary.agentSlug == 'workout-coach'
                    ? 'I adjusted the week and kept your recovery day intact.'
                    : summary.agentSlug == 'med-check'
                    ? 'I found a QT-related label warning. Confirm this medication '
                          'with her pharmacist and cardiology team before starting it.'
                    : 'I found the relevant details and summarized the next actions.',
                timestamp: summary.lastMessageAt,
              ),
            ],
    );
  }

  static WorkoutWeek get workoutWeek {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final monday = today.subtract(Duration(days: today.weekday - 1));
    final sessions = <int, PlannedSession>{
      0: const PlannedSession(sessionType: 'run', description: 'Easy run, 3 mi', targets: {}),
      2: const PlannedSession(sessionType: 'strength', description: 'Lower body', targets: {}),
      4: const PlannedSession(sessionType: 'run', description: 'Tempo run', targets: {}),
      5: const PlannedSession(sessionType: 'strength', description: 'Upper body', targets: {}),
      6: const PlannedSession(sessionType: 'rest', description: 'Rest day', targets: {}),
    };
    final days = <WorkoutDay>[];
    for (var offset = 0; offset < 7; offset++) {
      final date = monday.add(Duration(days: offset));
      final isToday = date == today;
      final planned = sessions[offset];
      final past = date.isBefore(today);
      List<LoggedWorkout> logs = const [];
      DayStatus status;
      if (past && planned != null && planned.sessionType != 'rest') {
        final positive = offset.isEven;
        logs = [
          LoggedWorkout(
            id: 'mock-log-$offset',
            activity: planned.sessionType,
            details: planned.sessionType == 'run'
                ? const {'distance_mi': 3.4, 'duration_min': 32}
                : const {
                    'exercises': [
                      {'name': 'squat', 'weight': 195, 'sets': 3, 'reps': 5},
                    ],
                  },
            notes: positive ? 'Felt strong.' : 'Tired today.',
            verdict: positive ? OverloadVerdict.positive : OverloadVerdict.negative,
            reason: positive ? '+0.4 mi at same pace vs last week' : '-5 lb squat vs last week',
          ),
        ];
        status = DayStatus.logged;
      } else if (planned == null) {
        status = DayStatus.empty;
      } else if (planned.sessionType == 'rest') {
        status = DayStatus.rest;
      } else if (isToday) {
        status = DayStatus.today;
      } else if (past) {
        status = DayStatus.missed;
      } else {
        status = DayStatus.upcoming;
      }
      days.add(WorkoutDay(
        date: date,
        isToday: isToday,
        planned: planned,
        logs: logs,
        status: status,
      ));
    }
    return WorkoutWeek(
      weekStart: monday,
      weekEnd: monday.add(const Duration(days: 6)),
      timezone: 'America/Chicago',
      planStatus: PlanStatus.active,
      days: days,
    );
  }
}
